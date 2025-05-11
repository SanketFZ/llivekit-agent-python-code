import asyncio
import os
import aiohttp
import json
import uuid
from pathlib import Path
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit import rtc
from livekit import api
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import deepgram, openai, silero, elevenlabs,google,cartesia

load_dotenv(dotenv_path='.env.local')


def read_prompt_from_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        return prompt_template
    except FileNotFoundError:
        print(f"Error: Prompt file '{filepath}' not found.")
        return None
    except Exception as e:
        print(f"Error reading prompt file: {e}")
        return None


prompt_file_path = "SalonKnowledgeBase.txt"
raw_prompt_template = read_prompt_from_file(prompt_file_path)


SALON_INFO = raw_prompt_template

class WarmHandoffAgent(Agent):
    def __init__(self, job_context=None) -> None:
        self.job_context = job_context
        super().__init__(
            instructions=SALON_INFO,
            stt=deepgram.STT(),
            llm=google.LLM(model="gemini-2.0-flash-exp",
             temperature=0.8,
    ),
            tts=cartesia.TTS(
      model="sonic-english",
      voice="c2ac25f9-ecc4-4f56-9095-651354df60c0",
      speed=0.8,
      emotion=["curiosity:highest", "positivity:high"],
   ),
            vad=silero.VAD.load()
        )

    @function_tool
    async def transfer_call(self, context: RunContext, phone_number: str):
        """
        Transfer the current call to a human agent at the specified phone number when you don't know the answer to the question or question asked is out of the contenxt
        
        Args:
            context: The call context
            phone_number: The phone number to transfer the call to 
        """
        if not self.job_context:
            await self.session.say("I'm sorry, I can't transfer the call at this time.")
            return None, "Failed to transfer call: No job context available"
            
        # Get room name from environment variable
        room_name = os.environ.get('LIVEKIT_ROOM_NAME', self.job_context.room.name)
        print(room_name)
        
        # Generate a unique identity for the SIP participant
        identity = f"transfer_{uuid.uuid4().hex[:8]}"
        
        # Create LiveKit API client
        livekit_url = os.environ.get('LIVEKIT_URL')
        livekit_api_key = os.environ.get('LIVEKIT_API_KEY')
        livekit_api_secret = os.environ.get('LIVEKIT_API_SECRET')
        sip_trunk_id = os.environ.get('SIP_TRUNK_ID')
        
        try:
            print(f"Transferring call to {phone_number}")
            
            # Using the API from the job context if available
            if self.job_context and hasattr(self.job_context, 'api'):
                response = await self.job_context.api.sip.create_sip_participant(
                    api.CreateSIPParticipantRequest(
                        sip_trunk_id=sip_trunk_id,
                        sip_call_to=phone_number,
                        room_name=room_name,
                        participant_identity=identity,
                        participant_name="Supervisor",
                        krisp_enabled=True
                    )
                )
            else:
                # Fallback to creating our own API client
                livekit_api = api.LiveKitAPI(
                    url=livekit_url,
                    api_key=livekit_api_key,
                    api_secret=livekit_api_secret
                )
                
                response = await livekit_api.sip.create_sip_participant(
                    api.CreateSIPParticipantRequest(
                        sip_trunk_id=sip_trunk_id,
                        sip_call_to=phone_number,
                        room_name=room_name,
                        participant_identity=identity,
                        participant_name="Supervisor",
                        krisp_enabled=True
                    )
                )
                
                await livekit_api.aclose()
            
            await self.session.say(f"I'm transferring you to a human agent now. Please hold while we connect you.")
            
            return None, f"I've transferred you to a human agent at {phone_number}. Please hold while we connect you."
            
        except Exception as e:
            print(f"Error transferring call: {e}")
            await self.session.say(f"I'm sorry, I couldn't transfer the call at this time.")
            return None, f"Failed to transfer call: {e}"
        
    @function_tool
    async def create_assistance_request(self, context: RunContext, original_question: str):
        """
        Use this function to create an assistance request for a supervisor to review 
        when you are unable to answer a user's question using your current knowledge base 
        or if the question is complex and requires human review. This will log the user's 
        question for later follow-up. Do not use this for immediate transfers; use 'transfer_call' for that.

        Args:
            context: The call context (automatically provided by the agent framework).
            original_question: The exact and complete question the user asked that you could not answer.
        """
        backend_url = os.environ.get('HELPREQUEST_BACKEND_URL')
        if not backend_url:
            print("Error: HELPREQUEST_BACKEND_URL environment variable not set.")
            await self.session.say("I'm sorry, I can't create an assistance request right now due to a system configuration issue.")
            return {"status": "failure", "reason": "Backend URL not configured."}

        if not self.job_context or not self.job_context.room:
            await self.session.say("I'm sorry, I'm missing some context to create the assistance request.")
            return {"status": "failure", "reason": "Job context or room info missing."}

        call_id = self.job_context.room.sid
        
        caller_id_to_use = f"unknown_caller_in_room_{call_id}" 
        participant_name_for_log = "Unknown Participant"

        remote_participants = list(self.job_context.room.remote_participants.values())
        if not remote_participants:
            print("Error: No remote participants found to identify the caller for assistance request.")
            # Agent should not create a request if it can't identify who it's for.
            await self.session.say("I'm sorry, I can't create an assistance request because I can't identify who is asking. Please ensure you're connected to the call.")
            return {"status": "failure", "reason": "No remote participant found."}

        user_participant = remote_participants[0] # Assuming the first remote participant is the user
        caller_id_to_use = user_participant.identity 
        participant_name_for_log = user_participant.name if user_participant.name else user_participant.identity
        
        if user_participant.metadata:
            try:
                metadata = json.loads(user_participant.metadata)
                phone_keys = ["number", "phoneNumber", "sip.callerid", "from_displayname", "Caller-Caller-ID-Number"] # Common keys
                for key in phone_keys:
                    if isinstance(metadata, dict) and key in metadata:
                        potential_phone_value = str(metadata[key])
                        # Basic validation for phone-like strings
                        cleaned_phone = "".join(filter(lambda char: char.isdigit() or char == '+', potential_phone_value.strip()))
                        if (cleaned_phone.startswith('+') and len(cleaned_phone) > 7) or \
                           (cleaned_phone.isdigit() and len(cleaned_phone) > 5 and len(cleaned_phone) < 16):
                            caller_id_to_use = potential_phone_value # Prefer parsed phone number
                            break 
            except json.JSONDecodeError:
                print(f"Warning: Could not parse metadata for participant {user_participant.identity}: {user_participant.metadata}")
            except Exception as e:
                print(f"Warning: Error processing metadata for {user_participant.identity}: {e}")

        payload = {
            "callId": call_id,
            "callerId": caller_id_to_use,
            "question": original_question,
        }

        print(f"Attempting to create assistance request for caller '{participant_name_for_log}' (ID: {caller_id_to_use}) with question: '{original_question}' to URL: {backend_url}")

        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(backend_url, json=payload, timeout=10) as response: # Added timeout
                    response_text = await response.text()
                    if response.status == 200 or response.status == 201: # HTTP OK or Created
                        try:
                            response_data = await response.json()
                            print(f"Successfully created assistance request: ID {response_data.get('id', 'N/A')}")
                            await self.session.say("Okay, I've logged your question for one of our team members to review. They'll look into it. Is there anything else I can help you with today?")
                            return {"status": "success", "request_id": response_data.get('id', 'N/A'), "message": "Assistance request created."}
                        except aiohttp.ContentTypeError: # If response is not JSON but status is 200/201
                             print(f"Successfully sent assistance request, but backend response was not JSON. Response: {response_text}")
                             await self.session.say("Okay, I've passed on your question to our team. Is there anything else I can assist with?")
                             return {"status": "success", "message": "Assistance request sent, non-JSON response from backend."}
                    else:
                        print(f"Error creating assistance request: HTTP {response.status} - {response_text}")
                        await self.session.say("I'm sorry, I wasn't able to log your question for a supervisor at this moment. You can try asking again later, or I can transfer you now.")
                        return {"status": "failure", "reason": f"HTTP {response.status} - {response_text}"}
        except aiohttp.ClientConnectorError as e:
            print(f"Network error creating assistance request: {e}")
            await self.session.say("I'm having trouble connecting to our support system right now. Please try again in a few moments.")
            return {"status": "failure", "reason": f"Network error: {e}"}
        except asyncio.TimeoutError:
            print(f"Timeout error creating assistance request to {backend_url}")
            await self.session.say("It's taking longer than expected to connect to our support system. Please try again shortly.")
            return {"status": "failure", "reason": "Request timed out."}
        except Exception as e:
            print(f"Unexpected error creating assistance request: {e}")
            await self.session.say("An unexpected error occurred while trying to log your question. If you need help, I can try transferring you.")
            return {"status": "failure", "reason": f"Unexpected error: {e}"}        
    async def on_enter(self):
        # Generate initial greeting
        self.session.generate_reply(
             instructions="Greet the user and offer your assistance."
        )

async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession()
    agent = WarmHandoffAgent(job_context=ctx)

    await session.start(
        agent=agent,
        room=ctx.room
    )

    def on_participant_connected_handler(participant: rtc.RemoteParticipant):
        asyncio.create_task(async_on_participant_connected(participant))
        
    async def async_on_participant_connected(participant: rtc.RemoteParticipant):
        await agent.session.say(f"Hi there! Is there anything I can help you with?")

    # Handle existing participants
    for participant in ctx.room.remote_participants.values():
        asyncio.create_task(async_on_participant_connected(participant))
    
    # Set up listener for new participants
    ctx.room.on("participant_connected", on_participant_connected_handler)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))