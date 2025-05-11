import { SipClient } from 'livekit-server-sdk';

const sipClient = new SipClient(process.env.LIVEKIT_URL,
                                process.env.LIVEKIT_API_KEY,
                                process.env.LIVEKIT_API_SECRET);

// An array of one or more provider phone numbers associated with the trunk.
const numbers = ['+15105550100'];

const name = 'My trunk';

// Trunk options
const trunkOptions = {
  allowed_numbers: ["+9356446546"],
  krispEnabled : true
};

const trunk = sipClient.createSipInboundTrunk(
  name,
  numbers,
  trunkOptions,
);

console.log(trunk);

