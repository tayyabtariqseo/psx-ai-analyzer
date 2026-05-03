from google import genai
import os
from dotenv import load_dotenv

# Load local .env file
load_dotenv()

import time

def analyze_with_ai(symbol, timeframe, indicator_data):
    """
    Sends technical data to Gemini for analysis.
    Includes fallback and retry logic for quota management.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "Error: Gemini API Key not found. Please set GOOGLE_API_KEY in .env or secrets."

    # List of models to try in order of preference
    # gemini-1.5-flash is the stable production model with higher quota limits
    models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro"]
    
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are a professional Fund Manager and Technical Analyst specializing in the Pakistan Stock Exchange (PSX).
    Analyze the following technical data for {symbol} on the {timeframe} timeframe:

    {indicator_data}

    Your task:
    1. Technical Score (0-100): Provide a score where 0 is extremely bearish and 100 is extremely bullish.
    2. Fund Manager Analysis: Provide a concise risk/reward assessment, identifying key levels, trend strength, and potential strategy (Buy/Sell/Hold/Wait).

    Keep the tone professional, objective, and data-driven.
    Format your response with clear headers.
    """

    last_error = ""
    for model_name in models_to_try:
        for attempt in range(2): # 2 attempts per model
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                last_error = str(e)
                if "429" in last_error:
                    time.sleep(2) # Short wait before retry
                    continue
                else:
                    break # Don't retry non-quota errors
    
    return f"AI Analysis is temporarily unavailable due to high demand (Quota reached). Please try again in 1 minute. \n\nDetails: {last_error}"
