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

# --- Example of using it ---
prompt_file_path = "SalonKnowledgeBase.txt"
raw_prompt_template = read_prompt_from_file(prompt_file_path)

if raw_prompt_template:
    # If your prompt has placeholders (like {{TEXT_TO_SUMMARIZE}}),
    # you'll need to replace them.
    document_content = "This is a very long and technical document about AI breakthroughs..." # Your actual document
    final_prompt = raw_prompt_template.replace("{{TEXT_TO_SUMMARIZE}}", document_content)

    print("--- Sending this prompt to the AI: ---")
    print(final_prompt)
    print("--------------------------------------")

    # Now you would send `final_prompt` to your AI model API
    # For example, using OpenAI's library:
    #
    # from openai import OpenAI
    # client = OpenAI(api_key="YOUR_API_KEY") # Make sure API key is set
    #
    # try:
    # response = client.chat.completions.create(
    # model="gpt-3.5-turbo", # Or any other model
    # messages=[
    # {"role": "user", "content": final_prompt}
    # ]
    # )
    # ai_response = response.choices[0].message.content
    # print("\nAI Response:", ai_response)
    # except Exception as e:
    # print(f"Error calling AI API: {e}")
    pass # Placeholder for actual API call