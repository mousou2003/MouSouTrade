"""This Python script provides examples on using the E*TRADE API endpoints"""
from __future__ import print_function
import webbrowser
import json
import logging
import configparser
import sys
import requests
from rauth import OAuth1Service
from logging.handlers import RotatingFileHandler
from accounts.accounts import Accounts
from market.market import Market

# loading configuration file
config = configparser.ConfigParser()
config.read(r'C:\Users\mouso\Documents\GitHub\MouSouTrade\marketdata_clients\EtradePythonClient\etrade_python_client\config.ini', encoding='utf-8')
print (config.sections())
print(config.get('DEFAULT', 'CONSUMER_KEY'))
print(config.get('DEFAULT', 'CONSUMER_SECRET'))
print(config.get('DEFAULT', 'SANDBOX_BASE_URL'))
print(config.get('DEFAULT', 'PROD_BASE_URL'))


# logger settings
logger = logging.getLogger('my_logger')
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler("python_client.log", maxBytes=5*1024*1024, backupCount=3)
FORMAT = "%(asctime)-15s %(message)s"
fmt = logging.Formatter(FORMAT, datefmt='%m/%d/%Y %I:%M:%S %p')
handler.setFormatter(fmt)
logger.addHandler(handler)


def oauth():
    """Allows user authorization for the sample application with OAuth 1"""
    etrade = OAuth1Service(
        name="etrade",
        consumer_key=config["DEFAULT"]["CONSUMER_KEY"],
        consumer_secret=config["DEFAULT"]["CONSUMER_SECRET"],
        request_token_url="https://api.etrade.com/oauth/request_token",
        access_token_url="https://api.etrade.com/oauth/access_token",
        authorize_url="https://us.etrade.com/e/t/etws/authorize?key={}&token={}",
        base_url="https://api.etrade.com")

    menu_items = {"1": "Sandbox Consumer Key",
                  "2": "Live Consumer Key",
                  "3": "Exit"}
    while True:
        print("")
        options = menu_items.keys()
        for entry in options:
            print(entry + ")\t" + menu_items[entry])
        selection = input("Please select Consumer Key Type: ")
        if selection == "1":
            base_url = config["DEFAULT"]["SANDBOX_BASE_URL"]
            break
        elif selection == "2":
            base_url = config["DEFAULT"]["PROD_BASE_URL"]
            break
        elif selection == "3":
            break
        else:
            print("Unknown Option Selected!")
    print("")

    try:
        # Step 1: Get OAuth 1 request token and secret
        request_token, request_token_secret = etrade.get_request_token(
            params={"oauth_callback": "oob", "format": "json"})
    except KeyError as e:
        if 'oauth_token' in str(e):
            print("Error: Consumer key rejected. Please check your credentials.")
            return
        else:
            raise

    # Step 2: Go through the authentication flow. Login to E*TRADE.
    # After you login, the page will provide a verification code to enter.
    authorize_url = etrade.authorize_url.format(etrade.consumer_key, request_token)
    webbrowser.open(authorize_url)
    text_code = input("Please accept agreement and enter verification code from browser: ")

    # Step 3: Exchange the authorized request token for an authenticated OAuth 1 session
    session = etrade.get_auth_session(request_token,
                                  request_token_secret,
                                  params={"oauth_verifier": text_code})

    main_menu(session, base_url)


def main_menu(session, base_url):
    """
    Provides the different options for the sample application: Market Quotes, Account List

    :param session: authenticated session
    """

    menu_items = {"1": "Market Quotes",
                  "2": "Account List",
                  "3": "Exit"}

    while True:
        print("")
        options = menu_items.keys()
        for entry in options:
            print(entry + ")\t" + menu_items[entry])
        selection = input("Please select an option: ")
        if selection == "1":
            market = Market(session, base_url)
            market.quotes()
        elif selection == "2":
            accounts = Accounts(session, base_url)
            accounts.account_list()
        elif selection == "3":
            break
        else:
            print("Unknown Option Selected!")


if __name__ == "__main__":
    oauth()
