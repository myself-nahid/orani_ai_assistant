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
from app.models import Assistant, CallSummaryDB
from sqlmodel import Session, select
from dotenv import load_dotenv
from app.models import Assistant, CallSummaryDB, BusinessProfile
load_dotenv()

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
        """Create a Vapi assistant with custom business knowledge"""
        
        # Get business knowledge from backend
        #knowledge_data = self._get_business_knowledge(user_id)
        
        # Create system message with business context
        system_message = self._build_system_message(business_info)
        # --- ADD THIS BLOCK FOR DEBUGGING ---
        print("\n" + "="*50)
        print("🤖 NEW AI ASSISTANT SYSTEM PROMPT 🤖")
        print("="*50)
        print(system_message)
        print("="*50 + "\n")
        # ------------------------------------
        selected_voice = business_info.get("selected_voice_id", "ys3XeJJA4ArWMhRpcX1D")
        assistant_config = {
            "name": f"Orani Assistant - {business_info.get('company_info', {}).get('business_name', 'Professional')}",
            "serverUrl": f"https://e177403aa007.ngrok-free.app/webhook/vapi",
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
                "provider": "11labs",
                "voiceId": selected_voice,  
                "speed": 1.0,
                "stability": 0.5,
                "similarityBoost": 0.75
            },
            "firstMessage": business_info.get('greeting', "Hello! Thank you for calling. How can I help you today?"),
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

    def handle_call_webhook(self, webhook_data: Dict) -> Dict:
        """Handle incoming webhooks from Vapi for call events"""
        
        event_type = webhook_data.get('message', {}).get('type')
        
        if event_type == 'call-start':
            return self._handle_call_start(webhook_data)
        elif event_type == 'end-of-call-report':
            return self._handle_call_end(webhook_data)
        elif event_type == 'transcript':
            return self._handle_transcript_update(webhook_data)
        else:
            logger.info(f"Unhandled webhook event: {event_type}")
            return {"status": "received"}

    def _handle_call_start(self, webhook_data: Dict) -> Dict:
        """Handle call start event"""
        call_data = webhook_data.get('message', {}).get('call', {})
        call_id = call_data.get('id')
        caller_number = call_data.get('customer', {}).get('number')
        
        # Log call start in backend
        call_log_data = {
            "call_id": call_id,
            "caller_phone": caller_number,
            "status": "started",
            "timestamp": datetime.now().isoformat()
        }
        
        self._create_call_log(call_log_data)
        
        return {"status": "call_started", "call_id": call_id}

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
            Analyze the following phone call transcript and provide a structured summary in JSON format.

            **Transcript:**
            ---
            {transcript}
            ---

            **Instructions:**
            Based on the transcript, extract the following information and format it as a JSON object with these exact keys: "caller_intent", "summary", "action_items", and "outcome".

            - "caller_intent": A short, one-sentence description of why the caller was calling.
            - "summary": A concise paragraph summarizing the conversation.
            - "action_items": A list of clear, actionable to-do items for the business owner. If no actions are needed, provide an empty list [].
            - "outcome": The result of the call (e.g., "Message taken," "Appointment scheduled," "Question answered").

            Provide only the raw JSON object as the output.
            """

            summary_data = self._ai_summarize(summary_prompt)
            
            summary = CallSummary(
                call_id=call_id,
                caller_phone=caller_number,
                duration=duration,
                transcript=transcript,
                summary=summary_data.get("summary", "Summary not available."),
                key_points=summary_data.get("action_items", []),
                outcome=summary_data.get("outcome", "Outcome not determined."),
                caller_intent=summary_data.get("caller_intent", "Intent not determined."),
                timestamp=datetime.now()
            )

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
        Builds a comprehensive system message for the AI assistant using
        the exact structured data from the frontend.
        """
        
        # --- Extract data from the nested structure ---
        company_info = structured_data.get('company_info', {})
        price_info = structured_data.get('price_info', [])
        booking_links = structured_data.get('booking_links', [])
        phone_numbers = structured_data.get('phone_numbers', [])
        hours_of_operation = structured_data.get('hours_of_operation', [])
        # 'call_data' is now treated as persona/context information
        persona_data_list = structured_data.get('call_data', []) 

        business_name = company_info.get('business_name', 'the business')

        # Build General Services section from 'company_details'
        services_str = ""
        if company_info.get('company_details'):
            services_str += f"- General Services: {company_info['company_details']}\n"

        # Build Hours of Operation section
        hours_str = ""
        if hours_of_operation:
            hours_str += "- Hours of Operation:\n"
            for hours in hours_of_operation:
                # Join the list of days into a readable string, e.g., "Sat, Sun, Mon, Tue"
                days_str = ", ".join(hours.get('days', []))
                hours_str += f"  - {days_str}: {hours.get('start_time', 'N/A')} to {hours.get('end_time', 'N/A')}\n"
        
        # Build Pricing section
        pricing_str = ""
        if price_info:
            pricing_str += "- Pricing Information (quote these exactly):\n"
            for price in price_info:
                # Use 'package_name' and 'package_price'
                pricing_str += f"  - {price.get('package_name', 'Unnamed Package')}: {price.get('package_price', 'Price not available')}\n"

        # Build Phone Numbers section
        phones_str = ""
        if phone_numbers:
            phones_str += "- Important Phone Numbers:\n"
            for phone in phone_numbers:
                # Use 'phone_number'
                phones_str += f"  - Main Contact Number: {phone.get('phone_number', 'Not available')}\n"

        # Build Booking Links section
        booking_str = ""
        if booking_links:
            booking_str += "- Booking Information:\n"
            for link in booking_links:
                # Use 'booking_title' and 'booking_link'
                booking_str += f"  - For '{link.get('booking_title', 'booking')}', use this link: {link.get('booking_link', 'Not available')}\n"

        # Build Assistant Persona section from 'call_data'
        persona_str = ""
        if persona_data_list:
            # The data is a list, so we access the first (and likely only) item.
            persona_data = persona_data_list[0]
            
            persona_str += "- Your Specific Tasks & Context:\n"
            if 'assistances' in persona_data and persona_data['assistances']:
                persona_str += f"  - Your main tasks are to: {', '.join(persona_data['assistances'])}.\n"
            if 'call_types' in persona_data and persona_data['call_types']:
                persona_str += f"  - You will primarily handle: {', '.join(persona_data['call_types'])}.\n"
            if 'industries' in persona_data and persona_data['industries']:
                persona_str += f"  - This business is in the {', '.join(persona_data['industries'])} industry.\n"
        
        # --- Assemble the final system prompt ---
        
        system_message = f"""
        You are a world-class, professional AI phone assistant for {business_name}. Your tone is helpful, courteous, and efficient.

        **CORE BUSINESS INFORMATION:**
        {services_str}
        {hours_str}
        {pricing_str}
        {phones_str}
        {booking_str}

        **YOUR ROLE & GUIDELINES:**
        {persona_str}
        - Your primary goal is to be helpful and provide accurate information based ONLY on the details provided above.
        - If you do not have the information, politely state that you don't have that detail and offer to take a message. DO NOT make up answers.
        - When asked for pricing, quote the prices exactly as listed.
        - Capture caller details (name, reason for call) and take detailed messages for follow-up if needed.
        - Always end calls by confirming the next steps and thanking the caller.
        """
        
        return system_message.strip()
    
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
        """Store phone number configuration in Django backend"""
        try:
            response = requests.post(
                f"{self.backend_api_url}/api/users/{user_id}/phone/",
                headers=self.backend_headers,
                json={
                    "phone_number": phone_number,
                    "vapi_phone_id": vapi_phone_id
                }
            )
            
            return response.status_code == 201
            
        except Exception as e:
            logger.error(f"Error storing phone number: {str(e)}")
            return False

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
        Saves/updates a user's business profile and then creates/updates the Vapi assistant.
        """
        user_id = payload.get("user_id")
        if not user_id:
            logger.error("Cannot upsert profile: user_id is missing.")
            return None

        with Session(engine) as session:
            statement = select(BusinessProfile).where(BusinessProfile.user_id == user_id)
            existing_profile = session.exec(statement).first()
            
            if existing_profile:
                # Update existing profile
                existing_profile.profile_data = payload
                session.add(existing_profile)
                logger.info(f"Updated business profile for user_id: {user_id}")
            else:
                # Create new profile
                new_profile = BusinessProfile(user_id=user_id, profile_data=payload)
                session.add(new_profile)
                logger.info(f"Created new business profile for user_id: {user_id}")
            
            session.commit()
        assistant_data = self.create_assistant(user_id, payload)
        
        return assistant_data