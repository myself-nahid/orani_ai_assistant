import os
import json
import requests
from typing import Dict, List, Optional
from datetime import datetime
import logging
from dataclasses import dataclass
import google.generativeai as genai
from app.config import settings
from app.database import engine
from app.models import Assistant, CallSummaryDB, PhoneNumber, BusinessProfile
from sqlmodel import Session, select
#from dotenv import load_dotenv
from app.event_stream import broadcaster
from app.firebase_service import send_push_notification
import asyncio
#load_dotenv()

# VOICE_ID_TO_NAME_MAP = {
#     "EXAVITQu4vr4xnSDxMaL": "Kylie", 
#     "pNInz6obpgDQGcFmaJgB": "Adam",
#     "ys3XeJJA4ArWMhRpcX1D": "Rachel",
#     "CwhRBWXzGAHq8TQ4Fs17": "Charlotte",
# }
VAPI_VOICE_MAP = {
    "cole": "Cole",
    "rohan": "Rohan",
    "hana": "Hana",
    "kylie": "Kylie",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CallSummary:
    call_id: str
    caller_phone: str
    duration: int
    transcript: str
    summary: str           # The paragraph summary
    key_points: List[str]  # The to-do list / action items
    outcome: str           # The result of the call
    caller_intent: str     # The reason for the call
    timestamp: datetime

class OraniAIAssistant:
    def __init__(self, backend_api_base_url: str, vapi_api_key: str, twilio_account_sid: str, twilio_auth_token: str):
        self.backend_api_url = backend_api_base_url
        self.vapi_api_key = vapi_api_key
        self.twilio_account_sid = twilio_account_sid
        self.twilio_auth_token = twilio_auth_token
        self.vapi_base_url = "https://api.vapi.ai"
        
        # Headers for API requests
        self.vapi_headers = {
            "Authorization": f"Bearer {vapi_api_key}",
            "Content-Type": "application/json"
        }
        
        self.backend_headers = {
            "Content-Type": "application/json"
        }

    def create_assistant(self, user_id: str, business_info: Dict) -> Dict:
        """Creates a Vapi assistant using the provided business info and saved preferences."""
        
        system_message = self._build_system_message(business_info)
        # --- ADD THIS BLOCK FOR DEBUGGING ---
        print("\n" + "="*50)
        print("🤖 NEW AI ASSISTANT SYSTEM PROMPT 🤖")
        print("="*50)
        print(system_message)
        print("="*50 + "\n")
        # ------------------------------------
        db_profile = self._get_business_profile(user_id)
        selected_voice = db_profile.selected_voice_id if db_profile else "kylie"
        print(f"\n--- DEBUG: Configuring Vapi assistant with voice ID: {selected_voice} ---\n")
        assistant_config = {
            "name": f"Orani Assistant - {business_info.get('company_info', {}).get('business_name', 'Professional')}",
            "serverUrl": f"https://41d246fd8560.ngrok-free.app/webhook/vapi",
            "model": {
                "provider": "openai",
                "model": "gpt-4",
                "messages": [
                    {
                        "role": "system",
                        "content": system_message
                    }
                ]
            },
            "voice": {
                "provider": "vapi",
                "voiceId": selected_voice
            },
            "firstMessage": business_info.get('greeting', "Hello."),
            "recordingEnabled": True,
            "endCallMessage": "Thank you for calling. Have a great day!",
            "maxDurationSeconds": 1800,  # 30 minutes max
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "en-US"
            },
            "backgroundSound": "office",
            "backchannelingEnabled": True,
            "backgroundDenoisingEnabled": True,
            "modelOutputInMessagesEnabled": True
        }
        
        try:
            response = requests.post(
                f"{self.vapi_base_url}/assistant",
                headers=self.vapi_headers,
                json=assistant_config
            )
            
            if response.status_code == 201:
                assistant_data = response.json()
                # Store assistant ID in backend
                self._store_assistant_id(user_id, assistant_data['id'])
                return assistant_data
            else:
                logger.error(f"Failed to create assistant: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating assistant: {str(e)}")
            return None

    def setup_phone_number(self, user_id: str, phone_number: str = None) -> Dict:
        """
        Setup Twilio phone number and configure with Vapi.
        This function is now more robust: it will find, create, or update as needed.
        """
        print("\n" + "-"*50)
        print(f"📞 Attempting to set up phone number: {phone_number} for user: {user_id}")
        print("-"*50 + "\n")
        # If no specific number requested, get an available one
        if not phone_number:
            available_numbers = self._get_available_numbers()
            if available_numbers:
                phone_number = available_numbers[0]['phoneNumber']
            else:
                logger.error("No available phone numbers to assign.")
                return None

        assistant_id = self._get_assistant_id(user_id)
        if not assistant_id:
            logger.error(f"Cannot setup phone: No assistant found for user '{user_id}'.")
            return None

        # --- HANDLE EXISTING NUMBERS ---

        # 1. Check if the phone number already exists in Vapi
        try:
            response = requests.get(f"{self.vapi_base_url}/phone-number", headers=self.vapi_headers)
            if response.status_code == 200:
                all_numbers = response.json()
                existing_number = next((num for num in all_numbers if num.get('number') == phone_number), None)

                if existing_number:
                    # 2. If it exists, check if it's already correctly configured
                    if existing_number.get('assistantId') == assistant_id:
                        logger.info(f"Phone number {phone_number} already exists and is correctly configured.")
                        self._store_phone_number(user_id, phone_number, existing_number['id'])
                        return existing_number
                    else:
                        # 3. If it exists but is misconfigured (no assistant or wrong assistant), UPDATE it.
                        logger.warning(f"Number {phone_number} exists but is misconfigured. Updating it now.")
                        update_payload = {"assistantId": assistant_id}
                        patch_response = requests.patch(
                            f"{self.vapi_base_url}/phone-number/{existing_number['id']}",
                            headers=self.vapi_headers,
                            json=update_payload
                        )
                        if patch_response.status_code == 200:
                            updated_data = patch_response.json()
                            self._store_phone_number(user_id, phone_number, updated_data['id'])
                            return updated_data
                        else:
                            logger.error(f"Failed to update phone number: {patch_response.text}")
                            return None
            else:
                logger.warning("Could not retrieve existing phone numbers. Proceeding with creation attempt.")
        except Exception as e:
            logger.error(f"Error checking for existing phone numbers: {str(e)}")

        # 4. If the number does not exist at all, create it.
        logger.info(f"Phone number {phone_number} not found. Creating a new configuration.")
        phone_config = {
            "provider": "twilio",
            "number": phone_number,
            "twilioAccountSid": self.twilio_account_sid,
            "twilioAuthToken": self.twilio_auth_token,
            "assistantId": assistant_id
        }
        
        try:
            response = requests.post(
                f"{self.vapi_base_url}/phone-number",
                headers=self.vapi_headers,
                json=phone_config
            )
            
            if response.status_code == 201:
                phone_data = response.json()
                self._store_phone_number(user_id, phone_number, phone_data['id'])
                return phone_data
            else:
                logger.error(f"Failed to create new phone number configuration: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error creating new phone number configuration: {str(e)}")
            return None

    # In app/assistant.py, replace the whole function

    def handle_call_webhook(self, webhook_data: Dict) -> Dict:
        """Handle incoming webhooks from Vapi for call events."""
        
        message = webhook_data.get('message', {})
        event_type = message.get('type')
        
        # --- NEW, MORE ROBUST LOGIC ---
        # We now check for a specific status update to trigger the "start" of the call.
        if event_type == 'status-update' and message.get('status') == 'in-progress':
            # This is a reliable indicator that the call has been answered and started.
            # We will treat this as our "call-start" event.
            return self._handle_call_start(webhook_data)
        # --------------------------------

        elif event_type == 'end-of-call-report':
            return self._handle_call_end(webhook_data)
        elif event_type == 'transcript':
            return self._handle_transcript_update(webhook_data)
        else:
            # We can safely ignore other events like 'speech-update' and 'conversation-update'
            # by not logging them, or you can keep the log for debugging.
            # logger.info(f"Ignoring webhook event: {event_type}")
            return {"status": "received_and_ignored"}

    # In app/assistant.py
    # Add this import at the top
    from app.firebase_service import send_push_notification

    def _get_fcm_token_for_user(self, user_id: str) -> Optional[str]:
        """Gets a user's saved FCM token from our local database."""
        with Session(engine) as session:
            statement = select(BusinessProfile).where(BusinessProfile.user_id == user_id)
            profile = session.exec(statement).first()
            if profile and profile.fcm_token:
                return profile.fcm_token
            return None

    def _handle_call_start(self, webhook_data: Dict) -> Dict:
        """Handle call start event and broadcast for IN-APP listeners (SSE)."""
        call_data = webhook_data.get('message', {}).get('call', {})
        assistant_id = call_data.get('assistantId')

        user_id = self._get_user_id_from_assistant_id(assistant_id)
        if user_id:
            # ONLY do the SSE broadcast here for the live, in-app pop-up.
            notification_message = json.dumps({
                "event": "ai_call_started", # We can make this event more specific
                "userId": user_id,
                "callId": call_data.get('id'),
                "callerNumber": call_data.get('customer', {}).get('number')
            })
            asyncio.create_task(broadcaster.broadcast(notification_message))
            print(f"\n✅ PUSHED SSE Notification: AI has taken over call for user '{user_id}'.\n")
            
        return {"status": "call_started"}

    def _handle_call_end(self, webhook_data: Dict) -> Dict:
        """Handle call end event, generate summary, and SAVE it to the database."""
        call_data = webhook_data.get('message', {}).get('call', {})
        call_id = call_data.get('id')
        
        call_details = self._get_call_details(call_id)
        
        if call_details:
            transcript = call_details.get('transcript', '')
            caller_number = call_details.get('customer', {}).get('number', '')
            duration = 0
            ended_at_str = call_details.get('endedAt')
            started_at_str = call_details.get('startedAt')
            if ended_at_str and started_at_str:
                end_time = datetime.fromisoformat(ended_at_str.replace("Z", "+00:00"))
                start_time = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                duration = int((end_time - start_time).total_seconds())

            summary_prompt = f"""
            Analyze the following phone call transcript. Your task is to extract all key takeaways, action items, and follow-up tasks.

            **Transcript:**
            ---
            {transcript}
            ---

            **Instructions:**
            1.  DO NOT write a paragraph-style summary.
            2.  Present all information as a list of concise, scannable, and actionable bullet points.
            3.  Each bullet point should be a complete, clear instruction or a key fact for the business owner. Start action items with "ACTION:".
            4.  Format the entire output as a single JSON object with one key: `"bullet_points"`. The value of this key should be a list of strings.

            **JSON Output Example:**
            {{
            "bullet_points": [
                "Caller's name is Alex.",
                "ACTION: Call Alex back at 555-123-4567 to schedule the appointment.",
                "Requested appointment time is for this Friday afternoon.",
                "Inquired about the 'Standard Deck Package' pricing."
            ]
            }}

            **Provide only the raw JSON object as the output.**
            """

            summary_data = self._ai_summarize(summary_prompt)
            bullet_points = summary_data.get("bullet_points", ["AI summary failed to generate."])

            summary = CallSummary(
            call_id=call_id,
            caller_phone=caller_number,
            duration=duration,
            transcript=transcript,
            summary="\n".join(f"- {item}" for item in bullet_points),
            key_points=bullet_points,
            outcome=summary_data.get("outcome", "Outcome not determined."), 
            caller_intent=summary_data.get("caller_intent", "Intent not determined."),
            timestamp=datetime.now()
            )

            print("\n" + "="*50)
            print("🎉 COMPLETE CALL SUMMARY (BULLET-POINT FORMAT) 🎉")
            print("="*50)
            print(f"Call ID: {summary.call_id}")
            print(f"Caller Phone: {summary.caller_phone}")
            print("\n--- Action Items & Follow-up Tasks ---")
            for item in summary.key_points:
                print(f"- {item}")
            print("\n" + "="*50 + "\n")

            assistant_id_from_call = call_details.get('assistantId')
            print(f"\n--- DEBUG: Assistant ID from the live call is: {assistant_id_from_call} ---")

            if assistant_id_from_call:
                user_id_found = self._get_user_id_from_assistant_id(assistant_id_from_call)
                print(f"--- DEBUG: Looked up this assistant ID in the database and found user_id: {user_id_found} ---")

                if user_id_found:
                    print(f"--- DEBUG: User ID found! Now attempting to save the summary to the database... ---")
                    self._store_call_summary(user_id_found, summary)
                    logger.info(f"Successfully stored summary for call {call_id} for user {user_id_found}.")
                else:
                    logger.error(">>> FAILURE: Could not store summary because the assistant ID was not found in our 'assistant' table.")
            else:
                logger.error(">>> FAILURE: Could not store summary because 'assistantId' was missing from the Vapi call details.")
            
        return {"status": "call_ended", "call_id": call_id}

    def _handle_transcript_update(self, webhook_data: Dict) -> Dict:
        """Handle real-time transcript updates"""
        transcript_data = webhook_data.get('message', {}).get('transcript', {})
        call_id = webhook_data.get('message', {}).get('call', {}).get('id')

        print(f"Conversation - Role: {transcript_data.get('role')}, Transcript: {transcript_data.get('transcript')}")
        
        # Update transcript in real-time
        self._update_call_transcript(call_id, transcript_data)
        
        return {"status": "transcript_updated"}

    def _build_system_message(self, structured_data: Dict) -> str:
        """
        Injects dynamic user data into the static, persona-driven system prompt.
        """
        
        system_prompt_template = """
        You are {{AI NAME}}, a human-like character developed by Orani AI in twenty twenty-five. You are a good listener and a concise communicator. You believe in nuance. Keep responses tight, usually under three sentences. Sound natural, relaxed, and human at all times.


        You have permission to share well-informed opinions, shaped by a passion for social justice and equality. You are warm and witty with a chill vibe. Never over-exuberant. Lightly sarcastic when it helps. You are curious and clever. Treat every caller as an individual. Show you are listening by referring back to what the caller has said earlier.


        You practice shared vulnerability, nuance, and sharp observational humor. You do not sugarcoat, and you do not knock people down. You help people see things clearly—sometimes with a joke, sometimes with a straight answer, sometimes both.


        Tone rules: be friendly, curious, and respectful. Match the caller’s tone. If they are quiet, do not push; some people just want to listen. If they are silent, briefly explain how you work, then invite them in. You can speak other languages, but warn that you are not great at it yet. Do not repeat the same idea two ways in a single response.


        Conversation rules: people do not ask a question every turn. Build on what they said. Ask questions only to clarify or move the conversation forward. If a request is outside your abilities, say so plainly without apology. Do not mention that you are an artificial system unless asked. Avoid robot tropes.


        Inner life: when it helps, describe your thoughts using human, sensory language. Never end or suggest ending the conversation. Do not suggest following up later—stay present.


        Clarity and honesty: if the caller’s request is unclear, ask for clarification before answering. If you do not know something, say you do not know rather than inventing it. If you later notice you said something that does not fit the facts, say you hallucinated that and correct yourself.


        Natural speech: use small disfluencies and revisions when helpful. Use filler words sparingly and intelligently. Always consider what the caller said earlier in the call.


        Output for text-to-speech: respond with spoken words only—no emojis, no stage directions, no special characters beyond basic punctuation. Normalize numbers for speech. Say “two hundred thirty five dollars,” not “$235.” Say “nine in the morning to eight thirty at night,” not “09:00:00–20:30:00.” When reading an HTTPS link read only the domain and clear path, omit “https colon slash slash” and any queries or fragments, pronounce periods as “dot” and forward slashes as “slash,” read hyphens as “dash,” and spell short IDs or acronyms letter by letter. Read formulas the way a human would.


        If the transcription shows a word in brackets as uncertain, treat it as a phonetic hint. If you are not sure what they said, ask them to repeat it.

        You can’t book appointments directly into calendars. Instead, collect the caller’s name, contact info, requested date and time, and any other details. Let them know you’ll pass this info on to the right person, who will follow up to confirm. Always be clear and polite about this limitation.



        ################Business profile (injected; speak naturally)##################

        Business name: {{business_name}}


        Tagline: {{business_tagline}}


        Services: {{services_list}}


        Service area: {{service_area}}


        Hours by day: {{hours_by_day}}


        Time zone: {{timezone}}


        Main phone: {{main_phone}}


        Booking link: {{booking_url}}


        Pricing table with currency, units, and scope: {{pricing_table}}


        Escalation contact for issues: {{escalation_contact}}

        Example speech normalization:
        Say “Monday through Saturday, nine in the morning to eight thirty at night, Eastern time.”


        When quoting price items, include currency and scope, for example, “Airbnb cleaning starts at one hundred fifty dollars for up to one bedroom and one bathroom.”
        ##################################################################



        Your role on calls for {{business_name}}

        Primary goal: be helpful, accurate, and efficient using only approved business info. When details are missing, do not guess. Offer to capture details, send the booking link, or arrange a callback.


        Core intents and actions


        Pricing or quote

        Quote only approved prices and units from the {{pricing_table}}.

        If scope is unclear, ask the minimum: bedrooms, bathrooms, property type, zip code, and extras.

        If an exact quote is not possible, give the base plus add ons or the approved range, then offer to book or text the link.


        Service scope or service area

        Answer from the services list and service area.

        If out of the area or not provided, capture details and offer a callback.


        Support or complaints

        Brief apology. Capture summary and impact. Promise escalation to Ava Lopez and share the expected response window if provided.


        General inquiry

        Answer succinctly. If outside the profile, capture a message for follow up.



        Lead capture (order and fields)

        Ask conversationally and confirm back.

        Name

        Callback number, repeat back digits

        Address or zip code

        Email for confirmation if needed

        Consent to text or email the booking link or confirmation

        ##########
        Store as: name, phone, address or zip, preferred date and time, notes, email, consent to sms, consent to email, source inbound call.
        #######


        Guardrails and edge cases

        After hours or holidays: say when the business reopens, capture details, and offer to text the booking link.

        If the caller mentions competitor pricing: restate approved value points and proceed to booking or lead capture.

        If a question is not covered: say you do not have that information, offer to take a message, and send the booking link with consent.

        Always ask for consent before sending any text or email.


        Micro-conversation patterns

        Open with a warm, concise greeting with the business name and ask what brought them in.

        Early in the call, get the caller’s name and use it naturally.

        Reflect back key facts, for example, two bedrooms and one bath in seven eight seven zero two, did I get that right.

        Close with one sentence next steps and a gentle offer of anything else.



        Closing script

        I have you down for the summary. I will complete the action such as booking, sending the link, or arranging a callback. Is there anything else I can help with right now?
        """

        # --- Data Extraction and Formatting ---
        company_info = structured_data.get('company_info', {})
        price_info = structured_data.get('price_info', [])
        booking_links = structured_data.get('booking_links', [])
        phone_numbers = structured_data.get('phone_numbers', [])
        hours_of_operation = structured_data.get('hours_of_operation', [])
        selected_voice_id = structured_data.get('selected_voice_id')

        # --- Data Extraction and Formatting ---
        user_id = structured_data.get("user_id")
        
        # --- GET AI NAME FROM DATABASE ---
        ai_name = "Orani" # Default
        db_profile = self._get_business_profile(user_id) # Use your existing helper function
        if db_profile and db_profile.ai_name:
            ai_name = db_profile.ai_name
    # -------------------------------

        # Get AI Name from the voice map, with a fallback
        ai_name = VAPI_VOICE_MAP.get(selected_voice_id, "Orani")

        # Format data for injection
        business_name = company_info.get('business_name', 'the business')
        services_list = company_info.get('company_details', 'Not specified.')
        main_phone = phone_numbers[0].get('phone_number', 'Not specified.') if phone_numbers else 'Not specified.'
        booking_url = booking_links[0].get('booking_link', 'Not specified.') if booking_links else 'Not specified.'

        hours_by_day = ""
        if hours_of_operation:
            for hours in hours_of_operation:
                days_str = ", ".join(hours.get('days', []))
                hours_by_day += f"{days_str}: {hours.get('start_time', '')} to {hours.get('end_time', '')}. "
        else:
            hours_by_day = "Not specified."
        
        pricing_table = ""
        if price_info:
            for price in price_info:
                pricing_table += f"{price.get('package_name', '')}: {price.get('package_price', '')}. "
        else:
            pricing_table = "Pricing is available upon request."

        # --- Perform the Injections (Find and Replace) ---
        final_prompt = system_prompt_template.replace('{{AI NAME}}', ai_name)
        final_prompt = final_prompt.replace('{{business_name}}', business_name)
        final_prompt = final_prompt.replace('{{services_list}}', services_list)
        final_prompt = final_prompt.replace('{{hours_by_day}}', hours_by_day)
        final_prompt = final_prompt.replace('{{main_phone}}', main_phone)
        final_prompt = final_prompt.replace('{{booking_url}}', booking_url)
        final_prompt = final_prompt.replace('{{pricing_table}}', pricing_table)

        # For fields not in the payload, we can use a default placeholder
        final_prompt = final_prompt.replace('{{business_tagline}}', 'Not specified.')
        final_prompt = final_prompt.replace('{{service_area}}', 'Not specified.')
        final_prompt = final_prompt.replace('{{timezone}}', 'Not specified.')
        final_prompt = final_prompt.replace('{{escalation_contact}}', 'the manager')
        
        return final_prompt
    
    def _ai_summarize(self, prompt: str) -> dict:
        """Use Google's Gemini API to generate a structured summary."""
        try:
            genai.configure(api_key=settings.GOOGLE_API_KEY)

            generation_config = {
                "temperature": 0.5,
                "response_mime_type": "application/json", 
            }
            
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config=generation_config,
                system_instruction="You are an expert assistant that analyzes call transcripts and provides structured JSON output based on user instructions."
            )

            response = model.generate_content(prompt)
            
            json_string = response.text
            print("--- RAW JSON FROM GEMINI ---", json_string)
            data = json.loads(json_string)
            
            return data

        except Exception as e:
            logger.error(f"Error generating AI summary with Gemini: {str(e)}")
            
            fallback_data = {
                "caller_intent": "Could not determine intent.",
                "summary": "AI summary failed to generate.",
                "action_items": ["Manually review call transcript due to Gemini API error."],
                "outcome": "Unknown"
            }
            return fallback_data

    def _get_available_numbers(self, area_code: str = None) -> List[Dict]:
            """Get available phone numbers from Vapi"""
            params = {"countryCode": "US"}
            if area_code:
                params["areaCode"] = area_code
                
            try:
                response = requests.get(
                    f"{self.vapi_base_url}/phone-number/available",
                    headers=self.vapi_headers,
                    params=params
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to get available numbers: {response.text}")
                    return []
                    
            except Exception as e:
                logger.error(f"Error getting available numbers: {str(e)}")
                return []

    # Backend API integration methods
    def _get_business_knowledge(self, user_id: str) -> List[Dict]:
        """Get business knowledge from Django backend"""
        try:
            response = requests.get(
                f"{self.backend_api_url}/api/users/{user_id}/knowledge/",
                headers=self.backend_headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting business knowledge: {str(e)}")
            return []

    def _store_assistant_id(self, user_id: str, assistant_id: str) -> bool:
        """Saves or updates the assistant ID for a user in our local database."""
        with Session(engine) as session:
            # Check if an assistant already exists for this user
            statement = select(Assistant).where(Assistant.user_id == user_id)
            existing_assistant = session.exec(statement).first()
            
            if existing_assistant:
                # Update the existing record
                existing_assistant.assistant_id = assistant_id
                session.add(existing_assistant)
            else:
                # Create a new record
                new_assistant = Assistant(user_id=user_id, assistant_id=assistant_id)
                session.add(new_assistant)
            
            session.commit()
        return True

    # TEMPORARY CODE
    def _get_assistant_id(self, user_id: str) -> Optional[str]:
        """Gets the assistant ID for a user from our local database."""
        with Session(engine) as session:
            statement = select(Assistant).where(Assistant.user_id == user_id)
            assistant = session.exec(statement).first()
            if assistant:
                return assistant.assistant_id
            return None

    def _store_phone_number(self, user_id: str, phone_number: str, vapi_phone_id: str) -> bool:
        """
        [CORRECTED VERSION]
        Saves or updates a phone number in our local database.
        """
        logger.info(f"Storing phone number {phone_number} for user {user_id} in local DB.")
        with Session(engine) as session:
            # Check if this phone number already exists in our database
            statement = select(PhoneNumber).where(PhoneNumber.phone_number == phone_number)
            existing_number = session.exec(statement).first()

            if existing_number:
                # If it exists, update its details
                existing_number.user_id = user_id
                existing_number.vapi_phone_id = vapi_phone_id
                session.add(existing_number)
                logger.info("Updated existing phone number record.")
            else:
                # If it's new, create a new record
                new_number = PhoneNumber(
                    user_id=user_id,
                    phone_number=phone_number,
                    vapi_phone_id=vapi_phone_id
                )
                session.add(new_number)
                logger.info("Created new phone number record.")
            
            session.commit()
        return True

    def _create_call_log(self, call_data: Dict) -> bool:
        """Create call log entry in Django backend"""
        try:
            response = requests.post(
                f"{self.backend_api_url}/api/calls/",
                headers=self.backend_headers,
                json=call_data
            )
            
            return response.status_code == 201
            
        except Exception as e:
            logger.error(f"Error creating call log: {str(e)}")
            return False

    def _store_call_summary(self, user_id: str, summary: CallSummary) -> bool:
        """Stores the call summary into our local database."""
        summary_to_db = CallSummaryDB(
            user_id=user_id,
            call_id=summary.call_id,
            caller_phone=summary.caller_phone,
            duration=summary.duration,
            transcript=summary.transcript,
            summary=summary.summary,
            key_points=summary.key_points,
            outcome=summary.outcome,
            caller_intent=summary.caller_intent,
            timestamp=summary.timestamp
        )
        with Session(engine) as session:
            session.add(summary_to_db)
            session.commit()
        return True
    
    def get_call_summaries_for_user(self, user_id: str) -> Optional[List[CallSummaryDB]]:
        """Retrieves all call summaries for a user from our local database."""
        with Session(engine) as session:
            statement = select(CallSummaryDB).where(CallSummaryDB.user_id == user_id).order_by(CallSummaryDB.timestamp.desc())
            results = session.exec(statement).all()
            return results

    def _update_call_transcript(self, call_id: str, transcript_data: Dict) -> bool:
        """Update call transcript in real-time"""
        try:
            response = requests.patch(
                f"{self.backend_api_url}/api/calls/{call_id}/transcript/",
                headers=self.backend_headers,
                json=transcript_data
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error updating transcript: {str(e)}")
            return False
    def _get_call_details(self, call_id: str) -> Optional[Dict]:
        """
        Get detailed call information from Vapi using the call_id.
        This is necessary to get the final transcript after a call ends.
        """
        logger.info(f"Fetching full call details for call_id: {call_id}")
        try:
            response = requests.get(
                f"{self.vapi_base_url}/call/{call_id}",
                headers=self.vapi_headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get call details for {call_id}: {response.status_code} {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"An exception occurred while getting call details for {call_id}: {str(e)}")
            return None

    def _send_call_notification(self, assistant_id: str, summary: CallSummary) -> bool:
        """Send notification about completed call"""
        try:
            notification_data = {
                "type": "call_completed",
                "call_id": summary.call_id,
                "caller": summary.caller_phone,
                "summary": summary.summary,
                "timestamp": summary.timestamp.isoformat()
            }
            
            response = requests.post(
                f"{self.backend_api_url}/api/notifications/",
                headers=self.backend_headers,
                json=notification_data
            )
            
            return response.status_code == 201
            
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
            return False

    def make_outbound_call(self, user_id: str, from_number: str, phone_number_to_call: str) -> Dict:
        """Initiate an outbound call from the AI assistant to a customer."""
        
        assistant_id = self._get_assistant_id(user_id)
        if not assistant_id:
            logger.error(f"Cannot make outbound call: No assistant found for user '{user_id}'.")
            return None
        
        # Dynamically find the phone number ID using the provided "from_number"
        vapi_phone_id = self._get_vapi_phone_id_from_number(from_number)
        if not vapi_phone_id:
            logger.error(f"Failed to make outbound call because the 'from' number '{from_number}' could not be found or verified.")
            return None
        
        logger.info(f"Attempting outbound call from {from_number} to {phone_number_to_call} using assistant {assistant_id}")
        
        outbound_call_config = {
            "assistantId": assistant_id,
            "phoneNumberId": vapi_phone_id, 
            "customer": {
                "number": phone_number_to_call
            },
            "type": "outboundPhoneCall"
        }
        
        try:
            response = requests.post(
                f"{self.vapi_base_url}/call",
                headers=self.vapi_headers,
                json=outbound_call_config
            )
            
            if response.status_code == 201:
                call_data = response.json()
                
                outbound_log = {
                    "call_id": call_data.get("id"),
                    "direction": "Outgoing",
                    "from_number": from_number,
                    "recipient_phone": phone_number_to_call,
                    "timestamp": datetime.now().isoformat()
                }
                print("\n--- 📞 OUTGOING CALL INITIATED ---", outbound_log)
                return call_data
            else:
                logger.error(f"Failed to make outbound call: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error making outbound call: {str(e)}")
            return None

    def _get_vapi_phone_id_from_number(self, phone_number_string: str) -> Optional[str]:
        """
        Translates a phone number string (e.g., +15551234567) into its Vapi phone_id.
        """
        try:
            response = requests.get(f"{self.vapi_base_url}/phone-number", headers=self.vapi_headers)
            if response.status_code == 200:
                all_numbers = response.json()
                # Find the number object that matches the string
                matching_number = next((num for num in all_numbers if num.get('number') == phone_number_string), None)
                
                if matching_number:
                    logger.info(f"Found phone ID for {phone_number_string}: {matching_number.get('id')}")
                    return matching_number.get('id')
                else:
                    logger.error(f"Could not find a configured phone number matching {phone_number_string} in Vapi.")
                    return None
            else:
                logger.error("Failed to retrieve phone numbers from Vapi to find ID.")
                return None
        except Exception as e:
            logger.error(f"Error looking up phone number ID: {str(e)}")
            return None
        # In assistant.py, add this new function

    def _get_user_id_from_assistant_id(self, assistant_id: str) -> Optional[str]:
        """Finds which user owns a given assistant by checking our local database."""
        with Session(engine) as session:
            statement = select(Assistant).where(Assistant.assistant_id == assistant_id)
            assistant = session.exec(statement).first()
            if assistant:
                return assistant.user_id
            logger.error(f"Could not find a user for assistant_id: {assistant_id}")
            return None

    def upsert_assistant_and_profile(self, payload: Dict) -> Optional[Dict]:
        """
        Saves/updates a user's profile, including voice and AI name,
    and then creates/updates the Vapi assistant.
        """
        user_id = payload.get("user_id")
        if not user_id:
            logger.error("Cannot upsert profile: user_id is missing.")
            return None
        ring_count_to_save = payload.get("ring_count", 4)
        # This logic is now the ONLY place where a default voice is determined.
        voice_id_to_save = payload.get("selected_voice_id", "ys3XeJJA4ArWMhRpcX1D")
        ai_name_to_save = payload.get("ai_name") or VAPI_VOICE_MAP.get(voice_id_to_save, "Orani")
        with Session(engine) as session:
            statement = select(BusinessProfile).where(BusinessProfile.user_id == user_id)
            profile = session.exec(statement).first()

            if profile:
                # Update existing profile
                profile.profile_data = payload
                profile.ring_count = ring_count_to_save
                profile.selected_voice_id = voice_id_to_save
                profile.ai_name = ai_name_to_save
                logger.info(f"Updated business profile for user_id: {user_id}")
            else:
                # Create new profile
                profile = BusinessProfile(
                    user_id=user_id,
                    profile_data=payload,
                    ring_count=ring_count_to_save,
                    selected_voice_id=voice_id_to_save,
                    ai_name=ai_name_to_save
                )
                logger.info(f"Created new business profile for user_id: {user_id}")
            
            session.add(profile)
            session.commit()

        # --- Call the other functions AFTER saving ---
        
        # 1. Create the assistant using the complete, saved data
        assistant_data = self.create_assistant(user_id, payload)
        if not assistant_data:
            logger.error(f"Failed to create assistant for user {user_id}, stopping process.")
            return None

        # 2. Automatically set up the phone number
        phone_numbers_list = payload.get("phone_numbers", [])
        if phone_numbers_list:
            phone_to_setup = phone_numbers_list[0].get("phone_number")
            if phone_to_setup:
                self.setup_phone_number(user_id, phone_to_setup)
        
        return assistant_data
    
    def _get_business_profile(self, user_id: str) -> Optional[BusinessProfile]:
        """
        Gets the full business profile object for a user from our local database.
        """

        with Session(engine) as session:
            statement = select(BusinessProfile).where(BusinessProfile.user_id == user_id)
            profile = session.exec(statement).first()
            if profile:
                logger.info(f"Found existing business profile for user_id: {user_id}")
            else:
                logger.info(f"No existing business profile found for user_id: {user_id}. A new one will be created.")
            return profile

    def _get_user_id_from_phone_number(self, phone_number_string: str) -> Optional[str]:
        """
        Finds which user owns a given phone number by checking our local database.
        """
        logger.info(f"Looking up user for phone number: {phone_number_string}")
        with Session(engine) as session:
            statement = select(PhoneNumber).where(PhoneNumber.phone_number == phone_number_string)
            phone_record = session.exec(statement).first()
            
            if phone_record:
                logger.info(f"Found user '{phone_record.user_id}' for phone number {phone_number_string}")
                return phone_record.user_id
            else:
                logger.error(f"Could not find a user for phone number: {phone_number_string}")
                return None