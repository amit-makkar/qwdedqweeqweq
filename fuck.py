# -*- coding: utf-8 -*-
import telebot
import requests
import json
import os
from time import time
import re
from telebot import types # Import types for InlineKeyboardMarkup

# --- CONFIGURATION ---
# 1. IMPORTANT: Your actual bot token has been inserted here.
BOT_TOKEN = '8520152230:AAEoBfi2YI_xsvvlAGdPvPFaEkG7zvRoIlc' 

# 2. API Settings
BASE_URL = "https://antifiednullapi.vercel.app/search"

# 3. Database File
USER_DB_FILE = 'users.json'
INITIAL_CREDITS = 50
LOOKUP_COST = 1
MAX_RECORDS_DISPLAY = 9999
MAX_TELEGRAM_MESSAGE_SIZE = 4000 # Must stay for safe message splitting

# FIX 1: Insert Bot Username with underscore for static link generation
OSINT_BOT_USERNAME = 'Osint_ok_robot'

# --- DATABASE / STATE MANAGEMENT ---

def load_users_db():
    """Loads user data from the JSON file. Initializes default admin/user if file is new."""
    global USER_DB_FILE # Ensure access to the global constant
    if not os.path.exists(USER_DB_FILE):
        # Default initialization with your specific Admin ID (1746944997)
        default = {
            '123456789': {'credits': 50, 'role': 'user'}, 
            '1746944997': {'credits': 9999, 'role': 'admin'} # Your Admin ID is hardcoded here
        }
        with open(USER_DB_FILE, 'w') as f:
            json.dump(default, f, indent=4)
        return default

    try:
        with open(USER_DB_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_users_db(db):
    """Saves user data back to the JSON file."""
    global USER_DB_FILE
    with open(USER_DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

def refund_credit(user_id, cost=LOOKUP_COST):
    """Reverts the credit deduction and saves the DB."""
    global USERS_DB
    global USER_DB_FILE
    if user_id in USERS_DB:
        USERS_DB[user_id]['credits'] += cost
        save_users_db(USERS_DB)
        print(f"[{user_id}] --- CREDIT REFUNDED: {cost} ---")
        return get_user_credits(user_id)
    return 0


# --- BOT INITIALIZATION ---
bot = telebot.TeleBot(BOT_TOKEN)
USERS_DB = load_users_db()

def get_user_id(message):
    """Gets the unique user identifier (as string)."""
    return str(message.chat.id)

def ensure_user_registered(user_id, referrer_id=None):
    """Initializes a new user with default credits if they don't exist, and processes referral."""
    global USERS_DB
    if user_id not in USERS_DB:
        USERS_DB[user_id] = {'credits': INITIAL_CREDITS, 'role': 'user'}
        
        # Process Referral (if valid and not self-referral)
        if referrer_id and referrer_id != user_id and referrer_id in USERS_DB:
            try:
                # Add 1 credit to the referrer's account
                USERS_DB[referrer_id]['credits'] += 1
                bot.send_message(referrer_id, 
                                 f"🎁 *Referral Bonus!* You received 1 credit for new user `{user_id}`\\.", 
                                 parse_mode='MarkdownV2')
            except Exception as e:
                print(f"[ERROR] Could not send referral message/credit: {e}")
                
        save_users_db(USERS_DB)

def get_user_credits(user_id):
    """Returns the user's current credit balance."""
    return USERS_DB.get(user_id, {}).get('credits', 0)

def get_user_role(user_id):
    """Returns the user's role."""
    return USERS_DB.get(user_id, {}).get('role', 'guest')

def is_admin(user_id):
    """Checks if the user has the 'admin' role."""
    return get_user_role(user_id) == 'admin'

# --- KEYBOARD GENERATION ---

def generate_search_menu():
    """Generates the inline keyboard for search types (Email removed)."""
    markup = types.InlineKeyboardMarkup()
    
    # Define search type buttons (Email removed)
    btn_mobile = types.InlineKeyboardButton("Mobile Search (mobile)", callback_data="search_mobile")
    btn_id = types.InlineKeyboardButton("ID Search (id)", callback_data="search_id")
    btn_alt = types.InlineKeyboardButton("Alternate Mobile (alt)", callback_data="search_alt")
    
    # Define new Invite button
    btn_invite = types.InlineKeyboardButton("Invite & Earn Credits", callback_data="show_invite_link")
    
    # Add buttons
    markup.add(btn_mobile, btn_id, btn_alt) # Row 1
    markup.add(btn_invite) # Row 2 (Invite)
    
    return markup

def generate_post_search_menu():
    """Generates the button to go back to the main search menu."""
    markup = types.InlineKeyboardMarkup()
    btn_start = types.InlineKeyboardButton("⬅️ Start New Search", callback_data="go_to_start")
    markup.add(btn_start)
    return markup


# --- MESSAGE SPLITTING UTILITY ---

def send_large_message(chat_id, text, parse_mode='MarkdownV2'):
    """Splits a large text into chunks and sends them sequentially."""
    global MAX_TELEGRAM_MESSAGE_SIZE
    
    # Check if splitting is necessary
    if len(text) <= MAX_TELEGRAM_MESSAGE_SIZE:
        bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=generate_post_search_menu()) # ADDED REPLY MARKUP HERE
        return

    # Split the text by a large separator (like record header) to ensure formatting integrity
    RECORD_SEPARATOR = '\n\-\-\- *RECORD No\\. '
    
    # Initial split (safe split points)
    record_chunks = text.split(RECORD_SEPARATOR)
    
    chunks = []
    current_chunk = record_chunks[0] # Start with header/metadata
    
    # Process the remaining chunks (records)
    for i in range(1, len(record_chunks)):
        record_header_and_body = RECORD_SEPARATOR + record_chunks[i]
        
        # Check if adding the next record will exceed the size limit
        if len(current_chunk) + len(record_header_and_body) > MAX_TELEGRAM_MESSAGE_SIZE:
            if current_chunk:
                chunks.append(current_chunk)
            
            # Start the new chunk with the current record
            current_chunk = record_header_and_body
        else:
            # Continue accumulating records in the current chunk
            current_chunk += record_header_and_body

    # Append the last accumulated chunk
    if current_chunk:
        chunks.append(current_chunk)
        
    # Send all chunks
    for i, chunk in enumerate(chunks):
        
        reply_markup = generate_post_search_menu() if i == len(chunks) - 1 else None
        
        # Add a continuation message only for subsequent parts
        if i > 0:
            bot.send_message(chat_id, f"--- PART {i + 1}/{len(chunks)} CONTINUED ---", parse_mode=None)
        
        # Send the main chunk (guaranteed not to break internal record formatting)
        bot.send_message(chat_id, chunk, parse_mode=parse_mode, reply_markup=reply_markup)
    
    print(f"Message split into {len(chunks)} parts and sent.")


# --- TELEGRAM COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'search'])
def handle_start(message):
    user_id = get_user_id(message)
    
    # Extract referrer ID from deep link (e.g., /start 1746944997)
    referrer_id = None
    args = message.text.split()
    if len(args) == 2 and args[0] == '/start':
        referrer_id = args[1]
        
    ensure_user_registered(user_id, referrer_id)
    credits = get_user_credits(user_id)
    
    response = (
        "*COSMOS INTEL PLATFORM*\n"
        "=========================\n"
        f"Hi, Welcome, {message.from_user.first_name}!\n\n"
        "This is a premium data access service using an external intelligence API.\n"
        "*Cost per Lookup:* 1 Credit\n"
        f"**Current Balance:** `{credits} credits`\n\n"
        "*Please select the type of data you want to search:* "
    )
    
    bot.send_message(message.chat.id, response, parse_mode='Markdown', reply_markup=generate_search_menu())

@bot.message_handler(commands=['credits'])
def handle_credits(message):
    user_id = get_user_id(message)
    ensure_user_registered(user_id)
    credits = get_user_credits(user_id)
    
    response = (
        "--- *CREDIT STATUS* ---\n"
        f"User ID: `{user_id}`\n"
        f"Role: *{get_user_role(user_id).upper()}*\n"
        f"Current Balance: *{credits} credits*\n"
        "═══════════════════════\n"
        "Need more credits? Contact the system administrator."
    )
    bot.send_message(message.chat.id, response, parse_mode='Markdown')

@bot.message_handler(commands=['invite'])
def handle_invite(message):
    user_id = get_user_id(message)
    global OSINT_BOT_USERNAME # Access the globally defined username
    
    response = (
        "*INVITE AND EARN CREDITS*\n"
        "=========================\n"
        "Earn 1 free lookup credit for every user you successfully refer!\n\n"
        "*Your Personal Referral Link:*\n"
        # FIX: Ensure correct username is used for the link
        f"https://t.me/{OSINT_BOT_USERNAME}?start={user_id}" 
    )
    bot.send_message(message.chat.id, response, parse_mode='Markdown')


@bot.message_handler(commands=['adminpanel'])
def handle_admin_panel(message):
    user_id = get_user_id(message)
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "Error: *ACCESS DENIED*: You must be an administrator to use this command\\.", parse_mode='MarkdownV2')
        return

    # FIX: Escaping all reserved characters in the static menu text
    response = (
        "*ADMINISTRATOR PANEL*\n"
        "\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\n"
        "Welcome Admin\\! Use the following commands to manage users and credits\\.\n\n"
        "\-\-\- *ADMIN COMMANDS* \-\-\-\n"
        "\* /setcredits \\<user\\_id\\> \\<amount\\>: Set a user's credit balance\\.\n"
        "   Example: `/setcredits 123456789 100`\n\n"
        "\* /bulkcredits \\<amount\\>: Set credits for ALL USERS\\.\n"
        "   Example: `/bulkcredits 50` \\(Sets all users to 50 credits\\)\n\n"
        "\* /listusers: View a list of all registered user IDs\\.\n"
        "\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-"
    )
    send_large_message(message.chat.id, response)


@bot.message_handler(commands=['listusers'])
def handle_list_users(message):
    user_id = get_user_id(message)
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "Error: *ACCESS DENIED*: You must be an administrator to use this command\\.", parse_mode='MarkdownV2')
        return

    users_list = ["--- *REGISTERED USERS* ---"]
    for uid, data in USERS_DB.items():
        role = data.get('role', 'user').upper()
        credits = data.get('credits', 0)
        users_list.append(f"ID: {uid} | Role: {role} | Credits: {credits}")
    
    bot.send_message(message.chat.id, "\n".join(users_list), parse_mode='Markdown')


@bot.message_handler(commands=['setcredits'])
def handle_set_credits(message):
    user_id = get_user_id(message)
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "🚫 *ACCESS DENIED*: You must be an administrator to use this command\\.", parse_mode='MarkdownV2')
        return
    
    try:
        args = message.text.split()
        if len(args) != 3:
            raise ValueError
        
        target_id = args[1]
        amount = int(args[2])
        
        if target_id not in USERS_DB:
            bot.send_message(message.chat.id, f"Error: User ID `{target_id}` not found in database\\.", parse_mode='MarkdownV2')
            return
            
        if amount < 0:
            bot.send_message(message.chat.id, "Error: Credit amount cannot be negative\\.", parse_mode='MarkdownV2')
            return

        # Update and save credits
        USERS_DB[target_id]['credits'] = amount
        save_users_db(USERS_DB)
        
        bot.send_message(message.chat.id, f"Success: Credits for user `{target_id}` set to **{amount}**\\.", parse_mode='MarkdownV2')
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Error: Invalid format\\. Usage: `/setcredits <user_id> <amount>`\nExample: `/setcredits 123456789 100`", parse_mode='MarkdownV2')

@bot.message_handler(commands=['bulkcredits'])
def handle_bulk_credits(message):
    user_id = get_user_id(message)
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "🚫 *ACCESS DENIED*: You must be an administrator to use this command\\.", parse_mode='MarkdownV2')
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            bot.send_message(message.chat.id, "❌ Error: Invalid format\\. Usage: `/bulkcredits <amount>`", parse_mode='MarkdownV2')
            return
        
        amount = int(args[1])
        if amount < 0:
            bot.send_message(message.chat.id, "Error: Credit amount cannot be negative\\.", parse_mode='MarkdownV2')
            return

        global USERS_DB
        users_count = 0
        
        # Apply bulk update to all users
        for uid in USERS_DB:
            USERS_DB[uid]['credits'] = amount
            users_count += 1
        
        save_users_db(USERS_DB)
        
        bot.send_message(message.chat.id, 
                         f"✅ *BULK UPDATE SUCCESS*: Set **{amount} credits** for **{users_count}** registered users\\.", 
                         parse_mode='MarkdownV2')
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Error: Invalid format\\. Amount must be a number\\.", parse_mode='MarkdownV2')
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Critical Error during bulk update: `{str(e)}`", parse_mode='MarkdownV2')


# --- CALLBACK QUERY HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('search_') or call.data == 'show_invite_link' or call.data == 'go_to_start')
def callback_search_type(call):
    # Check for Start Menu button click
    if call.data == 'go_to_start':
        bot.answer_callback_query(call.id, text="Returning to Main Menu.")
        # FIX: The menu needs to be resent, so we call handle_start
        bot.delete_message(call.message.chat.id, call.message.message_id)
        handle_start(call.message) 
        return
        
    # Check for referral invite button click
    if call.data == 'show_invite_link':
        bot.answer_callback_query(call.id, text="Your invite link is ready!")
        handle_invite(call.message)
        return
        
    search_type = call.data.split('_')[1] # Extracts mobile, id, or alt
    
    bot.answer_callback_query(call.id, text=f"Selected {search_type.upper()} Search. Ready for input.")
    
    # Delete the menu message to clean up the chat
    bot.delete_message(call.message.chat.id, call.message.message_id)

    prompt_message = (
        f"*{search_type.upper()} Search Selected*\n"
        "Please send the exact value you wish to look up now\\. "
        f"Example: `{get_example_value(search_type)}`"
    )
    
    sent_msg = bot.send_message(call.message.chat.id, prompt_message, parse_mode='MarkdownV2')
    
    # Register the next message from the user to be processed by process_search_query
    bot.register_next_step_handler(sent_msg, process_search_query, search_type=search_type)

def get_example_value(search_type):
    """Provides a relevant example based on search type."""
    # Email removed
    examples = {
        'mobile': '9161570798',
        'id': '492061614550',
        'alt': '9311881181'
    }
    return examples.get(search_type, "value")


# --- CORE LOOKUP FUNCTION (Called by next_step_handler) ---
def process_search_query(message, search_type):
    user_id = get_user_id(message)
    search_value = message.text.strip()
    
    if not search_value:
        bot.send_message(user_id, "Error: Search value cannot be empty. Please retry using /search.")
        return

    # Check credits again (just in case the user was slow and credits ran out)
    credits = get_user_credits(user_id)
    if credits < LOOKUP_COST:
        response = "Error: *Credit Limit Reached!* Your balance is too low. Please recharge."
        bot.send_message(user_id, response, parse_mode='Markdown')
        return
        
    print(f"[{user_id}] Lookup request received: {search_type}/{search_value}") # Internal Log

    # 3. Deduct Credit (optimistically before API call)
    global USERS_DB
    USERS_DB[user_id]['credits'] -= LOOKUP_COST
    save_users_db(USERS_DB)
    
    new_credits = get_user_credits(user_id)
    
    # Send immediate acknowledgment before API call starts (which can take 5+ seconds)
    ack_message = bot.send_message(user_id, f"Processing request... (Cost: {LOOKUP_COST} credit. New Balance: {new_credits})\n*Expecting high latency (~5-15s)*", parse_mode='Markdown')
    print(f"[{user_id}] Credit deducted. Starting API call for {search_type}/{search_value}") # Internal Log
    
    # 4. API Call
    global BASE_URL
    api_url = f"{BASE_URL}?{search_type}={search_value}"
    start_time = time()
    
    # Flag to track if credit needs to be refunded
    credit_refunded = False 

    try:
        headers = {
            'User-Agent': 'TelegramBot Client (Python cURL)',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
        }
        
        response = requests.get(api_url, headers=headers, timeout=15) 
        latency = time() - start_time
        
        # 5. Handle HTTP Errors (4xx, 5xx)
        if response.status_code >= 400:
            # --- REFUND CREDIT ---
            refund_credit(user_id)
            credit_refunded = True
            
            print(f"[{user_id}] API HTTP ERROR: {response.status_code}. Credit REFUNDED.") # Detailed Log
            
            # FIX: Simplified, robust error message for API failure (Avoids complex escaping)
            # The message is intentionally simple markdown (not V2) to avoid parsing failure
            response_text = (
                f"Search Failed: Not Found / Error (Status: {response.status_code})\n"
                "=========================\n"
                f"Query: *{search_type.upper()}* / `{search_value}`\n"
                "The external API returned an error status. Credit has been refunded."
            )
            # Sending as plain Markdown to prevent the V2 error on the final status message
            bot.send_message(user_id, response_text, parse_mode='Markdown') 
            return

        # 6. Handle Success and Format Output
        data = response.json()
        
        # Determine the actual payload, handling both dict (wrapped) and list (direct) responses
        if isinstance(data, dict):
            payload = data.get('api_data_payload', [])
        elif isinstance(data, list):
            payload = data
        else:
            payload = []
            
        print(f"[{user_id}] API Success. Latency: {latency:.2f}s. Records found: {len(payload) if isinstance(payload, list) else 0}") # Log success
        
        # Limit payload for display
        total_records = len(payload) if isinstance(payload, list) else 0
        
        if total_records == 0:
            # --- NOT FOUND RESPONSE (Success 200, but empty payload) ---
            response_text = (
                "🔎 *Search Result: Not Found*\n"
                "=========================\n"
                f"Query: *{search_type.upper()}* / `{search_value}`\n"
                "The external database returned no records for this query\\."
            )
            bot.send_message(user_id, response_text, parse_mode='MarkdownV2', reply_markup=generate_post_search_menu()) # ADDED REPLY MARKUP HERE
            return
            
        if total_records > MAX_RECORDS_DISPLAY:
            payload = payload[:MAX_RECORDS_DISPLAY]
            
        
        if not isinstance(payload, list):
             # --- REFUND CREDIT (Bad Payload) ---
            refund_credit(user_id)
            
            response_text = (
                f"\\(Warning\\) *Response Format Error* \\(Latency: `{latency:.2f}s`\\)\n"
                "API returned an unexpected data structure\\. *Credit has been refunded*\\."
            )
            raw_json_dump = json.dumps(data, indent=2)
            truncated_dump = raw_json_dump[:500] + ('\\.\\.\\.' if len(raw_json_dump) > 500 else '')
            response_text += f"\n\nRaw Data Sample:\n```json\n{truncated_dump}```"
            bot.send_message(user_id, response_text, parse_mode='MarkdownV2')
            return


        # Build structured results (VIP Layout)
        result_parts = [
            "\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=", 
            "*INTELLIGENCE REPORT*",
            f"🎯 Query Type: *{search_type.upper()}*",
            f"🔑 Query Value: `{search_value}`",
            "\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-", 
            f"Status: *SUCCESS* \\(Consumed: 1 Credit\\)",
            f"Latency: `{latency:.2f} seconds`",
            f"Records Found: *{total_records}*",
            "\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\=\n"
        ]

        # Structure individual records
        for i, record in enumerate(payload):
            record_str = f"\-\-\- *RECORD No\\. {i+1}* \-\-\-\n"
            
            for key, value in record.items():
                
                # Special formatting for long address strings
                if key == 'address' and isinstance(value, str):
                    address_parts = [p.strip() for p in value.split('!') if p.strip()]
                    value = ", ".join(address_parts)
                
                # Format key for display
                display_key = key.replace('_', ' ').title()
                
                # Escape characters for MarkdownV2 formatting
                # ESCAPE ALL RESERVED CHARACTERS IN DISPLAY KEY AND VALUE
                RESERVED_CHARS = ['\\', '`', '*', '_', '{', '}', '[', ']', '(', ')', '#', '+', '-', '.', '!']

                def escape_markdown_v2(text):
                    if not isinstance(text, str):
                        text = str(text)
                    for char in RESERVED_CHARS:
                        text = text.replace(char, f'\\{char}')
                    return text

                display_key = escape_markdown_v2(display_key)
                value_str = escape_markdown_v2(str(value))
                
                record_str += f"* {display_key}: `{value_str}`\n"
            
            result_parts.append(record_str)
            
        result_parts.append("\=\=\=\=\=\= END OF REPORT \=\=\=\=\=\=") 
            
        final_response = "\n".join(result_parts)
        
        # Send the final (potentially large) response using the splitting utility
        send_large_message(user_id, final_response, parse_mode='MarkdownV2')


    except requests.exceptions.Timeout:
        # --- REFUND CREDIT (Timeout) ---
        refund_credit(user_id)
        
        print(f"[{user_id}] ERROR: API TIMEOUT (> 15s). Credit REFUNDED.") # Log Timeout
        # FIX: Adding reply markup to timeout error
        bot.send_message(user_id, "Error: *Connection Timeout*: External API took too long to respond \\(> 15s\\)\\. *Credit has been refunded*\\.", parse_mode='MarkdownV2', reply_markup=generate_post_search_menu())
        
    except requests.exceptions.RequestException as e:
        # --- REFUND CREDIT (Network Error) ---
        refund_credit(user_id)
        
        print(f"[{user_id}] ERROR: NETWORK REQUEST EXCEPTION. Details: {e}. Credit REFUNDED.") # Log Network error
        bot.send_message(user_id, f"Error: *Network Error*: Could not connect to the API\\. *Credit has been refunded*\\.\nDetails: `{str(e)}`", parse_mode='MarkdownV2', reply_markup=generate_post_search_menu())
    
    except json.JSONDecodeError:
        # --- REFUND CREDIT (JSON Error) ---
        refund_credit(user_id)
        
        print(f"[{user_id}] ERROR: JSON DECODE FAILURE. Raw text was: {response.text[:50]}. Credit REFUNDED.") # Log JSON error
        bot.send_message(user_id, "Error: *Response Error*: API returned invalid data \\(Not JSON\\)\\. *Credit has been refunded*\\.", parse_mode='MarkdownV2', reply_markup=generate_post_search_menu())


# --- START BOT POLLING ---

# Check if the token is missing or if the placeholder is still present
if not BOT_TOKEN or 'YOUR_BOT_TOKEN' in BOT_TOKEN:
    print("FATAL ERROR: Bot Token is missing or invalid. Please ensure BOT_TOKEN is set correctly.")
else:
    # --- FIX ADDED: Delete Webhook before starting polling ---
    try:
        print("Checking for active webhook...")
        bot.delete_webhook()
        print("Webhook deleted successfully. Starting polling...")
    except Exception as e:
        print(f"Error deleting webhook (may be ignored if no webhook was set): {e}")

    bot.polling(none_stop=True)
