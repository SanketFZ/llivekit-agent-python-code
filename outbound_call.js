import { SipClient } from 'livekit-server-sdk';

const sipClient = new SipClient(process.env.LIVEKIT_URL,
                                process.env.LIVEKIT_API_KEY,
                                process.env.LIVEKIT_API_SECRET);

// SIP address is the hostname or IP the SIP INVITE is sent to.
// Address format for Twilio: <trunk-name>.pstn.twilio.com
// Address format for Telnyx: sip.telnyx.com
const address = 'myyyy.pstn.twilio.com';

// An array of one or more provider phone numbers associated with the trunk.
const numbers = ["+12494933052"];

// Trunk options
const trunkOptions = {
  auth_username: 'San@123ket',
  auth_password: 'Qwertyui@123'
};

const trunk = sipClient.createSipOutboundTrunk(
  'My trunk',
  address,
  numbers,
  trunkOptions
);