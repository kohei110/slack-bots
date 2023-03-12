import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from datetime import datetime, timedelta
from slack_sdk.errors import SlackApiError
import openai

import yaml
with open('config.yml', 'r') as f:
    config = yaml.safe_load(f)
    SLACK_APP_TOKEN = config['SLACK_APP_TOKEN']
    SLACK_BOT_TOKEN = config['SLACK_BOT_TOKEN']
    OPENAI_APIKEY = config['OPENAI_APIKEY']

    TXT_SELECT_CH = config['TXT_SELECT_CH']
    TXT_NOUPDATE = config['TXT_NOUPDATE']

openai.api_key = OPENAI_APIKEY

# Initializes your app with your bot token and socket mode handler
app = App(token=SLACK_BOT_TOKEN)

@app.event("message")
def message_hello(event, say, ack):
    channel_type = event["channel_type"]
    user_id = event["user"]

    # Set conversation scope to DM only
    if channel_type == "im":

        # Get channel list
        channels_list_response = app.client.conversations_list(types="public_channel,private_channel")
        channels = channels_list_response["channels"]
        bot_is_member_channels = [x for x in channels if x["is_member"] == True]

        # Create available channel list
        li_channel_options = [{"text": {"type": "plain_text", "text": c["name"]}, "value": c["id"]} for c in bot_is_member_channels]
        li_channel_id = [x["value"] for x in li_channel_options]

        # Create approved channel list
        li_approved_channel_ids = [] 
        for channel_id in li_channel_id:
            members = app.client.conversations_members(channel=channel_id)["members"]
            if user_id in members:
                li_approved_channel_ids.append(channel_id)

        selected_channels = [channel for channel in li_channel_options if channel['value'] in li_approved_channel_ids]
        
        say(
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"{TXT_SELECT_CH}"}, # first message from bot when you send DM
                    "accessory": {
                        "type": "static_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a channel",
                            "emoji": True
                        },
                        "options": selected_channels,
                        "action_id": "channel_select"
                    }
                }
            ],
            text=f"Hey there <@{event['user']}>!"
        )
    
    # Acknowledge the action
    ack()

@app.action("channel_select")
def select_channel(body, ack, say, client):
    try:
        # Get the selected channel ID
        selected_channel = body["actions"][0]["selected_option"]["value"]

        # Calculate the timestamp for 24 hours ago
        oldest = datetime.timestamp(datetime.now() - timedelta(hours=24))

        # Retrieve conversation history from the selected channel
        message_texts = []
        try:
            history = app.client.conversations_history(channel=selected_channel, oldest=oldest)
            messages = [m for m in history["messages"] if "bot_id" not in m]
            for m in messages:
                if "user" in m and "text" in m:
                    user_id = m["user"]
                    user_info = app.client.users_info(user=user_id)["user"]
                    if user_info["deleted"] or user_info["is_bot"]:
                        continue
                    username = user_info["name"]
                    message_text = m["text"]
                    ts = datetime.fromtimestamp(float(m["ts"])).strftime("%Y-%m-%d %H:%M:%S")
                    message_texts.append({'username': username, 'text': message_text, 'ts': ts})
        except SlackApiError as e:
            print(f"Error retrieving conversation history for channel {selected_channel}: {e}")
        
        if message_texts == []:
            summarised_txt = f'{TXT_NOUPDATE}'
        else:
            message_text_str = ""
            for item in message_texts:
                message_text_str += f"'{item['ts']}': {item['username']} said: '{item['text']}'\n"

            response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    temperature=0.7,
                    messages=[{
                        "role":
                        "system",
                        "content":
                        "\n".join([
                            'This chat log format is one line per message in the format "Time-stamp: Speaker name: Message".',
                            "The `\\n` within the message represents a line break."
                            f'The user understands Japanese only.',
                            f'So, The assistant need to speak in Japanese.',
                            f'Do not include greeting/salutation/polite expressions in summary',
                            f'Additionally, output must have followed format. The output must be starting from summary section, later it will be action items',
                            f'''something like 
                            【概要】
                            - Summary 1
                            - Summary 2
                            - Summary 3

                            【アクションアイテム】
                            - Action item 1
                            - Action item 2
                            ''',
                            f'please use following text input as input chat log',
                            f'{message_text_str}',
                            f'please make sure output text is written in Japanese'
                        ])
                    }]
                    )



            summarised_txt = response["choices"][0]["message"]['content']

        # Send a message with the conversation history
        say(
            blocks=[

                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"```{summarised_txt}```"}
                }
            ]
        )
    except Exception as e:
        print(f"Error: {e}")

    # Acknowledge the action
    ack()

# Start your app
if __name__ == "__main__":  
    SocketModeHandler(app, SLACK_APP_TOKEN).start()