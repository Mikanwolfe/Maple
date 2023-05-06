import discord
from discord.ext import commands

# Configure simple discord bot
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!',intents=intents)

# Maple uses the ChatGPT Wrapper to manage conversations. More information can be found at https://github.com/mmabrouk/chatgpt-wrapper
from chatgpt_wrapper import OpenAIAPI
from chatgpt_wrapper.core.config import Config
from chatgpt_wrapper.backends.openai.user import UserManager
from chatgpt_wrapper.backends.openai.database import Database

# System prompts (SP) and Reminder prompts (RP) have been stored in separate python files for convenience as they are quite long
# It is easier to edit and interact with system prompts in this form rather than through a JSON file, which can't have multiline strings 
from system_prompt import sp, rp

import json

with open("settings.json", "r") as f:
    settings = json.load(f)

with open("credentials.json", "r") as f:
    credentials = json.load(f)

# Set the configuration for ChatGPT. Higher values = more creative responses.
#  The freq and presence penalty have been set high to encourage new conversation and limit highly unhinged interactions.
#  My running idea is that a low freq and pres penalty may lead to more spicy interactions with the provided prompts.
config = Config()
config.set('chat.model_customizations.model', settings['chatgpt_model'])
config.set('chat.model_customizations.temperature', settings['chatgpt_temp'])
config.set('chat.model_customizations.frequency_penalty', settings['chatgpt_freq'])
config.set('chat.model_customizations.presence_penalty', settings['chatgpt_pres'])

# ChatGPT Wrapper
bot = OpenAIAPI(config)
database = Database(config)
database.create_schema()
user_management = UserManager(config)
session = user_management.orm.session

# Set system prompt
bot.set_model_system_message("".join(sp))

# Attempts at getting a natural language response from ChatGPT
# The goal is to have Maple reply with "My status is STATUS"
# This has had limited success
def get_config_reply(ctx):
    reply = f"""
    ```
    temperature: {config.get('chat.model_customizations.temperature')}
    frequency_penalty: {config.get('chat.model_customizations.frequency_penalty')}
    presence_penalty: {config.get('chat.model_customizations.presence_penalty')}
    ```
    """
    return reply

def get_new_convo(ctx):
    return "TODO: Actions for a new conversation"

def get_status_info(ctx):
    return "TODO: Actions for status"

# Define the dictionary with keyword-value pairs
keyword_dict = {
    "CONFIG": get_config_reply,
    "NEWCONVO": get_new_convo,
    "STATUSINFO": get_status_info
}

# Rotation function for reminder prompts
def next_string(my_list):
    if not hasattr(next_string, "index"):
        next_string.index = 0
    if next_string.index >= len(my_list):
        next_string.index = 0
    string = my_list[next_string.index]
    next_string.index += 1
    return string

# Log into the chatgpt wrapper with a default user
success, user, message = user_management.login(settings['chatgpt_wrapper_user'], settings['chatgpt_wrapper_pw'])
if not success:
    print("Login unsuccessful, attempting to register a new user")
    success, user, message = user_management.register(settings['chatgpt_wrapper_user'], settings['chatgpt_wrapper_email'], settings['chatgpt_wrapper_pw'])


bot.set_current_user(user)
print("Successfully logged in as " + str(user))
# Run gateway prompts
# I know this isn't the most ideal, however, in our testing, this worked well at producing significant personality and character

for prompt in settings['gateway_prompts']:
    msg_content = prompt
    success, response, errmsg = bot.ask(msg_content)
    if success:
        print(f"Message sent to Maple: [{msg_content}] \n Maple Response: [{response}]")
    else:
        raise RuntimeError(errmsg)

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

@client.event
async def on_message(message):
    # Do not allow the bot to reply to itself. It may, however, reply to other bots.
    #  Highly recommended to reply to other bots. It's very amusing.
    if message.author.id == client.user.id:
        return
    
    # Limit Maple to channels
    if not (message.channel.id in settings['allowed_channels'] or isinstance(message.channel, discord.DMChannel)):
        return
    

    ctx = await client.get_context(message)
    async with ctx.typing():


        # compose a ChatGPT Query
        msg_content = f"SYSTEM {next_string(rp)} {settings['pre_prompt']} : CH {message.channel.id} : "

        # Yes there is an OR we could use like name = nick or name, but we want to split the tag (e.g. Maple#1234 -> Maple)
        # This is also easier to read for anyone who wants to adjust.
        if (hasattr(message.author, 'nick')):
            if (message.author.nick is None):
                msg_content = msg_content + "USER " +str(message.author).split("#")[0] + " : "+ message.content
            else:
                msg_content = msg_content + "USER " +message.author.nick + " : " + message.content
        else:
            msg_content =  msg_content + "USER " +str(message.author).split("#")[0] + " : "+ message.content

        # Query ChatGPT
        success, response, errmsg = bot.ask(msg_content)

        print(f"Message: [{msg_content}] | Reply [{response}]")
        if success:
            if (response.startswith('REPLY') or response.startswith('Maple')):

                # Remove the common missteps. Honestly got lazy here
                sent_response = str(response).replace("REPLY: ", "").replace("REPLY ", "").replace("Maple: ", "").replace("Reply: ", "").replace("Reply ", "")

                # Replace keywords in the response with their associated values
                for key, value in keyword_dict.items():
                    sent_response = sent_response.replace(key, str(value(ctx)))

                await message.channel.send(sent_response)
            else:
                print("Maple sent a NOREPLY") # Log to console
        else:
            raise RuntimeError(errmsg)
        
    await client.process_commands(message)

@client.command()
async def restart(ctx):
    bot.new_conversation()
    for prompt in settings['gateway_prompts']:
        msg_content = prompt
        success, response, errmsg = bot.ask(msg_content)
        if success:
            print(f"Message sent to Maple: [{msg_content}] \n Maple Response: [{response}]")
        else:
            raise RuntimeError(errmsg)

    await ctx.send('Maple restarted!')

client.run(credentials['discord_api_token'])