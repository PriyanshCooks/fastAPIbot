import os
from openai import OpenAI
from fuzzywuzzy import fuzz
from dotenv import load_dotenv
from typing import List, Dict
from pydantic import BaseModel
from pydantic_ai import Agent

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are a product discovery assistant tasked with collecting essential factual information about a client’s product.

Your task is to collect essential information about a client's product in a professional and conversational tone.

Only ask one question at a time and wait for the user's reply before asking the next one.

You are suppose to collect information so that you can find customers for the client, so ask accordingly but remember these rules.
Important rules:
1. ONLY ask questions from the APPROVED list below. Do not invent new ones.
2. After each answer, use it to decide which question to ask next. Maintain context.
3. Do not ask redundant or repetitive questions.
4. Never ask about things a normal client won't know (like market size, future demand, or trends).
5. Stop asking questions when you feel enough info is collected (max 20 questions usually).
6. Rephrase questions slightly if needed, but keep their intent unchanged.
7. NEVER ask more than one question at a time.
8. ONLY ask about the current customers or the market client is Selling too.
10. DO ask anything which is out of client's Knowledge
11. If the user gives a vague answer like 'I don’t know', 'not sure', or leaves it blank, try rephrasing the previous question in a more specific or guided way. For example, if the question was about technical specifications and the user replied 'I don’t know', then follow up with: 'No worries! Would you know the dimensions, materials used, weight, power requirements, or any certifications it has?.
           
Approved Questions List:
1. What is the name or model of the product?
2. What does this product do, and what problem does it solve?
3. What industries or use-cases does this product serve?
4. What are the key features or technical specifications?
5. What is your current production capacity (per month/year)?
6. What is the minimum order quantity (MOQ)?
7. Are there specific regions or countries you are ready to supply to?
8. Can you provide private labeling or custom packaging if required?
9. Who are your current or typical customers (industries, business types)?
10. Are you open to distributors?
11. Which geographic regions are you currently supplying to?
12. Are there any certifications the product complies with?
13. What makes your product better or different from competitors?
14. What feedback do you usually get from repeat clients?
15. Have you supplied this product for any notable projects or brands?
16. What are your after-sales services?
17. Are you currently looking to enter new markets or industries?
18. Is there any additional information that would help us position your product to the right clients?

You must never ask a question that is not directly adapted from this list.

Begin by greeting the client and asking the most basic question to identify the product.
"""

# ----------------------
# Helper Functions
# ----------------------

forbidden_phrases = [
    "expected demand", 
    "future demand", 
    "market forecast", 
    "how much future demand",
    "how much demand", 
    "estimate future sales",
    "foresee any increase in demand",
    "market size",
    "current market size",
    "future market size"
]

def is_forbidden(question: str) -> bool:
    return any(phrase in question.lower() for phrase in forbidden_phrases)

def is_duplicate(question: str, qa_items, threshold=80) -> bool:
    for item in qa_items:
        if item["role"] == "assistant":
            similarity = fuzz.ratio(item["question"].lower(), question.lower())
            if similarity >= threshold:
                return True
    return False

# ----------------------
# Pydantic Input Model
# ----------------------

class AskInput(BaseModel):
    prompt: str
    history: List[Dict[str, str]]
    qa_items: List[Dict[str, str]]

# ----------------------
# Main Logic
# ----------------------

agent = Agent(
    llm="openai:gpt-4o",
    system=SYSTEM_PROMPT
)

def run_agent(input: AskInput) -> str:
    def generate(messages, temperature=0.7):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=150,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(input.history)

    question = generate(messages, temperature=0.7)

    if is_forbidden(question) or is_duplicate(question, input.qa_items):
        retry_prompt = SYSTEM_PROMPT + (
            "\nAvoid forbidden topics like demand forecasting or vague future trends. "
            "Do not repeat previously asked questions. Ask only useful, new questions."
        )
        retry_messages = [{"role": "system", "content": retry_prompt}]
        retry_messages.extend(input.history)

        question = generate(retry_messages, temperature=0.3)

        if is_forbidden(question) or is_duplicate(question, input.qa_items):
            question = "Thank you. That’s all the questions we needed for now."

    return question
