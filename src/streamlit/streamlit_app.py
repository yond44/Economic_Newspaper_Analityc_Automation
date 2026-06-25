"""
Streamlit Dashboard for Jojoba Economic News
- Email CRUD Management
- Manual Question Submission with Multi-Email Support
"""
import streamlit as st
import requests
import json
from datetime import datetime
import time
import os
from pathlib import Path
from dotenv import load_dotenv

# ============================================
# LOAD ENVIRONMENT VARIABLES
# ============================================
# Get the project root
CURRENT_DIR = Path(__file__).parent  # src/streamlit/
PROJECT_ROOT = CURRENT_DIR.parent.parent  # Project root

# Load .env from project root
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    print(f"⚠️ No .env file found at: {env_path}")

# ============================================
# CONFIGURATION - READ FROM .env
# ============================================
API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1/agent")
API_KEY = os.getenv("GROQ_API_KEY", "")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/ask")

# ============================================
# PAGE CONFIG
# ============================================
st.set_page_config(
    page_title="Jojoba Economic News - Admin",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# SIDEBAR - Navigation
# ============================================
st.sidebar.title("📊 Jojoba Economic News")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["📧 Email Management", "📝 Submit Question"]
)

st.sidebar.markdown("---")

# Show status in sidebar
try:
    response = requests.get(
        f"{API_URL}/status",
        headers={"X-API-Key": API_KEY},
        timeout=2
    )
    if response.status_code == 200:
        st.sidebar.success("✅ API Connected")
    else:
        st.sidebar.error(f"❌ API Error: {response.status_code}")
except Exception as e:
    st.sidebar.error(f"❌ API Offline: {str(e)}")

st.sidebar.caption(f"API: {API_URL}")
st.sidebar.caption(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ============================================
# PAGE: EMAIL MANAGEMENT
# ============================================
if page == "📧 Email Management":
    st.title("📧 Email Contact Management")
    st.caption("Manage email recipients for Economic News reports")
    
    # Initialize session state for email data
    if 'emails_data' not in st.session_state:
        st.session_state.emails_data = None
        st.session_state.last_refresh = None
    
    # Manual refresh button - THIS IS THE ONLY WAY TO REFRESH
    col_refresh, col_info = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh Data", use_container_width=True):
            with st.spinner("Loading contacts..."):
                try:
                    response = requests.get(
                        f"{API_URL}/emails",
                        headers={"X-API-Key": API_KEY}
                    )
                    if response.status_code == 200:
                        st.session_state.emails_data = response.json()
                        st.session_state.last_refresh = datetime.now()
                        st.success("✅ Data refreshed!")
                    else:
                        st.error(f"Failed to fetch contacts: {response.status_code}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    with col_info:
        if st.session_state.last_refresh:
            st.caption(f"Last updated: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    
    st.divider()
    
    # Add new contact
    with st.expander("➕ Add New Contact", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Name", key="new_name")
        with col2:
            new_email = st.text_input("Email", key="new_email")
        
        if st.button("Add Contact", key="add_contact_btn"):
            if new_name and new_email:
                with st.spinner("Adding contact..."):
                    try:
                        response = requests.post(
                            f"{API_URL}/emails",
                            params={"name": new_name, "email": new_email},
                            headers={"X-API-Key": API_KEY}
                        )
                        if response.status_code == 200:
                            st.success("✅ Contact added successfully! Click 'Refresh Data' to see changes")
                            # Clear the form
                            st.session_state.new_name = ""
                            st.session_state.new_email = ""
                        else:
                            st.error(f"Failed to add contact: {response.text}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
            else:
                st.warning("Please fill in both name and email")
    
    # Display contacts - ONLY from session state
    if st.session_state.emails_data:
        emails = st.session_state.emails_data.get("emails", [])
        st.info(f"📬 Total contacts: {len(emails)}")
        
        if emails:
            for email in emails:
                col1, col2, col3, col4 = st.columns([2, 3, 2, 1])
                
                with col1:
                    st.write(f"**{email.get('name')}**")
                with col2:
                    st.write(email.get('email'))
                with col3:
                    st.caption(f"ID: {email.get('id')}")
                with col4:
                    if st.button("🗑️", key=f"delete_{email.get('id')}"):
                        with st.spinner("Deleting..."):
                            try:
                                delete_response = requests.delete(
                                    f"{API_URL}/emails/{email.get('id')}",
                                    headers={"X-API-Key": API_KEY}
                                )
                                if delete_response.status_code == 200:
                                    st.success("✅ Deleted! Click 'Refresh Data' to update the list")
                                    # Clear cached data to force refresh on next load
                                    st.cache_data.clear()
                                else:
                                    st.error("Failed to delete")
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
                
                st.divider()
            
            # Show email string for n8n
            st.subheader("📧 Email String for n8n")
            email_string = ", ".join([e.get("email") for e in emails if e.get("email")])
            st.code(email_string, language="text")
            
            # Reset button
            if st.button("🔄 Reset to Default Contacts", use_container_width=True):
                with st.spinner("Resetting..."):
                    try:
                        reset_response = requests.post(
                            f"{API_URL}/emails/reset",
                            headers={"X-API-Key": API_KEY}
                        )
                        if reset_response.status_code == 200:
                            st.success("✅ Reset successfully! Click 'Refresh Data' to update the list")
                            st.cache_data.clear()
                        else:
                            st.error("Failed to reset")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        else:
            st.info("No contacts found. Add some!")
    else:
        st.info("👆 Click 'Refresh Data' to load contacts")
        st.caption("Or add a new contact above and then refresh")

# ============================================
# PAGE: SUBMIT QUESTION
# ============================================
elif page == "📝 Submit Question":
    st.title("📝 Submit Economic Question")
    st.caption("Submit a question manually to get an economic analysis")
    
    if 'submit_success' not in st.session_state:
        st.session_state.submit_success = None
        st.session_state.submit_data = None
        st.session_state.last_submit = None
    
    if 'contacts_data' not in st.session_state:
        st.session_state.contacts_data = []
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 Load Contacts", use_container_width=True):
            with st.spinner("Loading contacts..."):
                try:
                    email_response = requests.get(
                        f"{API_URL}/emails",
                        headers={"X-API-Key": API_KEY}
                    )
                    if email_response.status_code == 200:
                        email_data = email_response.json()
                        st.session_state.contacts_data = email_data.get("emails", [])
                        st.success(f"✅ Loaded {len(st.session_state.contacts_data)} contacts")
                    else:
                        st.error("Failed to load contacts")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    with col2:
        if st.session_state.contacts_data:
            st.caption(f"📬 {len(st.session_state.contacts_data)} contacts loaded")
        else:
            st.caption("Click 'Load Contacts' to get email list")
    
    st.divider()
    
    st.subheader("✍️ Your Question")
    question = st.text_area(
        "Enter your economic question:",
        placeholder="e.g., What is the current BI rate and its impact on the Rupiah?",
        height=100,
        key="question_input"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📧 Send To")
        
        selected_emails = []
        
        if st.session_state.contacts_data:
            email_options = [f"{c.get('name')} ({c.get('email')})" for c in st.session_state.contacts_data]
            
            selected_options = st.multiselect(
                "Select recipients",
                options=email_options,
                default=[],
                help="Select one or more recipients",
                key="recipient_select"
            )
            
            for option in selected_options:
                if "(" in option and ")" in option:
                    email = option.split("(")[1].split(")")[0]
                    selected_emails.append(email)
            
            if selected_emails:
                st.success(f"✅ {len(selected_emails)} recipient(s) selected")
                for email in selected_emails:
                    st.caption(f"📧 {email}")
            else:
                st.warning("⚠️ No recipients selected")
        else:
            st.warning("⚠️ No contacts loaded. Click 'Load Contacts' above.")
            selected_emails = []
    
    with col2:
        st.subheader("📱 Phone (Optional)")
        phone = st.text_input(
            "Phone number with country code:",
            placeholder="e.g., 6281234567890",
            help="e.g., 6281234567890 for Indonesia",
            key="phone_input"
        )
        st.caption("This will send the answer via WhatsApp too")
        
        st.subheader("🔧 Delivery Method")
        use_n8n = st.checkbox(
            "Use n8n workflow (instead of direct API)",
            value=False,
            help="Check this to send through n8n webhook instead of direct API",
            key="use_n8n_checkbox"
        )
    
    if st.session_state.submit_success is not None:
        if st.session_state.submit_success:
            st.success("✅ Last submission successful!")
            if st.session_state.last_submit:
                st.caption(f"Submitted at: {st.session_state.last_submit.strftime('%H:%M:%S')}")
        else:
            st.error("❌ Last submission failed")
    
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        submit_disabled = not question or not selected_emails or not st.session_state.contacts_data
        if st.button("🚀 Submit & Send Analysis", type="primary", disabled=submit_disabled, use_container_width=True):
            with st.spinner("Processing your question..."):
                try:
                    payload = {
                        "question": question,
                        "emails": selected_emails,
                        "phone": phone if phone else ""
                    }
                    
                    if use_n8n:
                        n8n_payload = {
                            "question": question,
                            "email": ", ".join(selected_emails),
                            "phone": phone if phone else ""
                        }
                        response = requests.post(
                            N8N_WEBHOOK_URL,
                            json=n8n_payload,
                            headers={"Content-Type": "application/json"}
                        )
                        endpoint_used = "n8n"
                    else:
                        response = requests.post(
                            f"{API_URL}/send-batch",
                            json=payload,
                            headers={
                                "Content-Type": "application/json",
                                "X-API-Key": API_KEY
                            }
                        )
                        endpoint_used = "FastAPI"
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.submit_success = True
                        st.session_state.submit_data = data
                        st.session_state.last_submit = datetime.now()
                        
                        if data.get('simulated', False):
                            st.warning("⚠️ Email sending is in simulation mode (SMTP not configured)")
                            st.info("📧 Emails were logged but not actually sent")
                        
                        st.success("✅ Question submitted successfully!")
                        st.info(f"📋 Question: {question[:100]}..." if len(question) > 100 else f"📋 Question: {question}")
                        st.info(f"🔗 Via: {endpoint_used}")

                        with st.expander("📧 Email Delivery Details", expanded=True):
                            total = data.get('total_recipients', len(selected_emails))
                            sent = data.get('sent_count', 0)
                            failed = data.get('failed_emails', [])
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Total Recipients", total)
                            with col2:
                                st.metric("Sent Successfully", sent)
                            with col3:
                                st.metric("Failed", len(failed))
                            
                            st.divider()
                            
                            st.write("**Individual Status:**")
                            for email in selected_emails:
                                if email in failed:
                                    st.error(f"❌ Failed: {email}")
                                else:
                                    st.success(f"✅ Sent: {email}")
                            
                            if data.get('message'):
                                st.info(f"ℹ️ {data.get('message')}")
                        
                        if phone:
                            st.info(f"📱 WhatsApp sent to: {phone}")
                        
                        st.balloons()
                    else:
                        st.session_state.submit_success = False
                        st.error(f"❌ Failed to submit: {response.status_code}")
                        try:
                            st.json(response.json())
                        except:
                            st.text(response.text)
                        
                except requests.exceptions.ConnectionError:
                    st.session_state.submit_success = False
                    st.error("❌ Connection error - is the server running?")
                    st.info("Start FastAPI with: python -m src.main")
                except Exception as e:
                    st.session_state.submit_success = False
                    st.error(f"❌ Error: {str(e)}")
    
    st.divider()
    st.subheader("📊 Current Queue Status")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 Refresh Queue"):
            with st.spinner("Loading queue..."):
                try:
                    response = requests.get(
                        f"{API_URL}/queue",
                        headers={"X-API-Key": API_KEY}
                    )
                    if response.status_code == 200:
                        st.session_state.queue_data = response.json()
                        st.success("✅ Queue updated!")
                    else:
                        st.error("Failed to get queue status")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    with col2:
        if 'queue_data' in st.session_state and st.session_state.queue_data:
            st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
    
    if 'queue_data' in st.session_state and st.session_state.queue_data:
        queue_data = st.session_state.queue_data
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Questions in Queue", queue_data.get("total", 0))
        with col2:
            next_q = queue_data.get("next", "None")
            st.metric("Next Question", next_q[:50] + "..." if next_q and len(next_q) > 50 else next_q or "None")
    else:
        st.info("👆 Click 'Refresh Queue' to load queue status")

# ============================================
# FOOTER
# ============================================
st.sidebar.markdown("---")
st.sidebar.caption("Jojoba Economic News v1.0")
st.sidebar.caption("Made with ❤️")