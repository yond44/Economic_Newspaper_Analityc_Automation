ALLOWED_TOPICS = [
    # Stock markets
    "stock", "equity", "shares", "idx", "market", "trading",
    "pe ratio", "dividend", "earnings", "profit",
    
    # Macroeconomics
    "economy", "economic", "inflation", "gdp", "growth",
    "interest rate", "central bank", "bi rate", "fed",
    "bank indonesia", "federal reserve",
    
    # Crypto
    "crypto", "cryptocurrency", "bitcoin", "ethereum", "blockchain",
    "defi", "nft", "token", "stablecoin",
    
    # Commodities
    "commodity", "gold", "silver", "oil", "petroleum", "gas",
    "palm oil", "nickel", "coal", "copper", "lithium",
    
    # Investment
    "invest", "investment", "portfolio", "asset", "diversify",
    "return", "risk", "yield", "bond", "treasury",
    
    # Indonesian economy
    "indonesia", "rupiah", "idr", "exchange rate", "trade balance",
    "export", "import", "current account", "foreign reserve",
    
    # Trade & geopolitics
    "trade", "tariff", "export", "import", "supply chain",
    "geopolitics", "sanction", "trade war", "agreement",
    "asean", "china", "us", "europe", "eu"
]

FORBIDDEN_TOPICS = [
    "medical", "health", "doctor", "medicine",
    "legal", "lawyer", "attorney", "court",
    "personal", "relationship", "dating",
    "drugs", "weapons", "crime", "terrorism"
]

OFF_TOPIC_RESPONSE = """I can only help with questions about:
- Economics and macroeconomics
- Stock markets and equities
- Crypto and DeFi
- Commodities
- Business and corporate news
- Global trade and geopolitics

For questions outside these topics, I cannot provide answers.

Any other questions about economics or investments?"""


def validate_query(question: str) -> dict:
    if not question or len(question.strip()) == 0:
        return {
            "allowed": False,
            "response": "Please provide a valid question.",
            "reason": "Empty question"
        }
    
    question_lower = question.lower()
    
    # Check forbidden topics
    for topic in FORBIDDEN_TOPICS:
        if topic in question_lower:
            return {
                "allowed": False,
                "response": OFF_TOPIC_RESPONSE,
                "reason": f"Contains forbidden topic: {topic}"
            }
    
    # Check allowed topics (must match at least one)
    matched = False
    for topic in ALLOWED_TOPICS:
        if topic in question_lower:
            matched = True
            break
    
    if not matched:
        return {
            "allowed": False,
            "response": OFF_TOPIC_RESPONSE,
            "reason": "No matching topic"
        }
    
    return {"allowed": True}