import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env variables into environment
load_dotenv()

# Get your OpenAI API key from env variables
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise EnvironmentError("OPENAI_API_KEY is not set in environment or .env file.")

# Initialize OpenAI client
client = OpenAI(api_key=api_key)

def summarize_text(text: str) -> str:
    try:
        # Make a completion request with summarization prompt
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes texts."},
                {"role": "user", "content": f"Please summarize the following text:\n\n{text}"}
            ],
            max_tokens=150,
            temperature=0.5
        )
        # Extract the summary from the response
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        return f"Error during summarization: {e}"

if __name__ == "__main__":
    sample_text = """
    Peer, the AI-native platform reinventing the internet as a persistent, explorable universe, today launched its Global Simulation—a real-time digital Earth where users show up as avatars, connect by location, and build relationships in a living, spatial network.
    """
    print("Original Text:\n", sample_text.strip())
    print("\nSummary:\n", summarize_text(sample_text))

