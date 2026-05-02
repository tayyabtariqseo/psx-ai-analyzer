import google.generativeai as genai
import os

def analyze_with_ai(symbol, timeframe, indicator_data):
    """
    Sends technical data to Gemini for analysis.
    Returns a combined report (Score + Narrative).
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "Error: Gemini API Key not found. Please set GOOGLE_API_KEY in secrets."

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-pro')

    # Construct the prompt
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

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error during AI analysis: {str(e)}"
