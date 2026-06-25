"""
Question Manager - Simple TXT-based queue with data-driven question generation
"""
import os
import logging
import random
import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================
# FILE PATHS
# ============================================
CURRENT_DIR = Path(__file__).parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

QUESTION_FILE = PROJECT_ROOT / "question_queue.txt"
ARCHIVE_FILE = PROJECT_ROOT / "answered_questions_archive.txt"

logger.info(f"📁 Project root: {PROJECT_ROOT}")
logger.info(f"📁 Question file: {QUESTION_FILE}")
logger.info(f"📁 Archive file: {ARCHIVE_FILE}")


# ============================================
# DATA LOADING
# ============================================
def load_data_files() -> Dict[str, Any]:
    """Load data from the data files for question generation"""
    data = {
        "topics": [],
        "sectors": [],
        "companies": [],
        "indicators": [],
        "commodities": [],
        "events": [],
        "regions": []
    }
    
    try:
        # Load from deep_dive_reports.txt
        data_dir = PROJECT_ROOT / "data" / "raw"
        deep_dive_file = data_dir / "deep_dive_reports.txt"
        
        if deep_dive_file.exists():
            with open(deep_dive_file, 'r') as f:
                content = f.read()
                # Extract topics
                topics = re.findall(r'\[TOPIC: (.*?)\]', content)
                data["topics"] = list(set(topics))
        
        # Load from structured_analysis.txt
        structured_file = data_dir / "structured_analysis.txt"
        if structured_file.exists():
            with open(structured_file, 'r') as f:
                for line in f:
                    if '|' in line:
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= 3:
                            category = parts[0].strip()
                            title = parts[2].strip() if len(parts) > 2 else ""
                            if category and category not in ["CATEGORY", "---", ""]:
                                data["topics"].append(f"{category}: {title}")
        
        # Load from quant_financial_data.txt
        quant_file = data_dir / "quant_financial_data.txt"
        if quant_file.exists():
            with open(quant_file, 'r') as f:
                content = f.read()
                # Extract sectors from TABLE 1
                sector_match = re.search(r'TABLE 1:.*?\n(.*?)\n\n', content, re.DOTALL)
                if sector_match:
                    lines = sector_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'SECTOR' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['SECTOR', '']:
                                data["sectors"].append(parts[0])
                
                # Extract commodities
                commodity_match = re.search(r'TABLE 3:.*?\n(.*?)\n\n', content, re.DOTALL)
                if commodity_match:
                    lines = commodity_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'COMMODITY' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['COMMODITY', '']:
                                data["commodities"].append(parts[0])
                
                # Extract companies from TABLE 8
                company_match = re.search(r'TABLE 8:.*?\n(.*?)\n\n', content, re.DOTALL)
                if company_match:
                    lines = company_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'COMPANY' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['COMPANY', '']:
                                data["companies"].append(parts[0])
                
                # Extract indicators from TABLE 5
                indicator_match = re.search(r'TABLE 5:.*?\n(.*?)\n\n', content, re.DOTALL)
                if indicator_match:
                    lines = indicator_match.group(1).split('\n')
                    for line in lines:
                        if '|' in line and 'INDICATOR' not in line and '------' not in line:
                            parts = [p.strip() for p in line.split('|')]
                            if parts and parts[0] and parts[0] not in ['INDICATOR', '']:
                                data["indicators"].append(parts[0])
        
        # Clean up
        data["topics"] = [t for t in data["topics"] if t and len(t) > 5][:50]
        data["sectors"] = list(set([s for s in data["sectors"] if s and len(s) > 2]))[:20]
        data["companies"] = list(set([c for c in data["companies"] if c and len(c) > 2]))[:20]
        data["commodities"] = list(set([c for c in data["commodities"] if c and len(c) > 2]))[:15]
        data["indicators"] = list(set([i for i in data["indicators"] if i and len(i) > 5]))[:20]
        
        # Add some regions
        data["regions"] = ["Indonesia", "US", "China", "ASEAN", "Europe", "Japan", "India", "Singapore"]
        
        # Add some events
        data["events"] = [
            "BI rate decision", "Fed meeting", "inflation release", "GDP report", 
            "trade balance announcement", "earnings season", "IPO pipeline", 
            "central bank intervention", "commodity price rally", "market correction"
        ]
        
        logger.info(f"📊 Loaded {len(data['topics'])} topics, {len(data['sectors'])} sectors, {len(data['companies'])} companies")
        return data
        
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return data


# Load data once
DATA = load_data_files()


def initialize_question_file():
    """Create the question file with default questions if it doesn't exist"""
    if not QUESTION_FILE.exists():
        default_questions = [
            "What is the current BI rate and what is its impact on the Rupiah exchange rate?",
            "What is the latest core inflation rate in Indonesia and how does it compare to BI's target?",
            "What is the current GDP growth forecast for Indonesia and key drivers?",
            "What are the latest policy signals from Bank Indonesia regarding future rates?",
            "What is the Federal Reserve's latest stance on interest rates and inflation?",
            "What is the current US inflation rate and its impact on global markets?",
            "What is the latest ECB policy decision and its effect on the Euro?",
            "What is the Bank of Japan's current monetary policy stance?",
            "What is the latest JCI (IDX Composite) performance and key movers?",
            "What are the top 5 performing stocks on IDX this week?",
            "What is the current foreign flow into Indonesian stock market?",
            "What are the latest earnings reports from major Indonesian banks?"
        ]
        
        with open(QUESTION_FILE, 'w') as f:
            for q in default_questions:
                f.write(q + '\n')
        
        logger.info(f"✅ Created question file with {len(default_questions)} questions at: {QUESTION_FILE}")
        return len(default_questions)
    
    count = get_question_count()
    logger.info(f"📄 Question file exists with {count} questions at: {QUESTION_FILE}")
    return count


def get_question_count() -> int:
    """Get number of questions in queue"""
    if not QUESTION_FILE.exists():
        return 0
    
    with open(QUESTION_FILE, 'r') as f:
        return len([line for line in f if line.strip()])


def get_next_question() -> Optional[str]:
    """Get the first question from the queue (index 0)"""
    if not QUESTION_FILE.exists():
        initialize_question_file()
    
    with open(QUESTION_FILE, 'r') as f:
        questions = [line.strip() for line in f if line.strip()]
    
    if not questions:
        return None
    
    return questions[0]


def remove_first_question() -> bool:
    """Remove the first question from the queue"""
    if not QUESTION_FILE.exists():
        return False
    
    with open(QUESTION_FILE, 'r') as f:
        questions = [line.strip() for line in f if line.strip()]
    
    if not questions:
        return False
    
    archive_question(questions[0])
    questions = questions[1:]
    
    with open(QUESTION_FILE, 'w') as f:
        for q in questions:
            if q.strip():
                f.write(q + '\n')
    
    return True


def add_question(question: str):
    """Add a question to the end of the queue"""
    if not question or not question.strip():
        return
    
    question = question.strip()
    if not question.endswith('?'):
        question += '?'
    
    with open(QUESTION_FILE, 'a') as f:
        f.write(question + '\n')
    
    logger.info(f"➕ Added question: {question[:50]}...")


def archive_question(question: str):
    """Archive answered question"""
    with open(ARCHIVE_FILE, 'a') as f:
        timestamp = datetime.now().isoformat()
        f.write(f"{timestamp} | {question}\n")


def get_all_questions() -> List[str]:
    """Get all questions in the queue"""
    if not QUESTION_FILE.exists():
        return []
    
    with open(QUESTION_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def get_archive() -> List[str]:
    """Get all archived questions"""
    if not ARCHIVE_FILE.exists():
        return []
    
    with open(ARCHIVE_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def reset_question_queue():
    """Reset the queue to default questions"""
    if QUESTION_FILE.exists():
        QUESTION_FILE.unlink()
    
    if ARCHIVE_FILE.exists():
        ARCHIVE_FILE.unlink()
    
    return initialize_question_file()


def generate_new_question_from_data() -> Optional[str]:
    """
    Generate a diverse question based on actual data from the files
    """
    try:
        # Pick random elements from our data
        topic = random.choice(DATA["topics"]) if DATA["topics"] else "Indonesian economy"
        sector = random.choice(DATA["sectors"]) if DATA["sectors"] else "banking"
        company = random.choice(DATA["companies"]) if DATA["companies"] else "major companies"
        commodity = random.choice(DATA["commodities"]) if DATA["commodities"] else "commodities"
        indicator = random.choice(DATA["indicators"]) if DATA["indicators"] else "economic indicators"
        region = random.choice(DATA["regions"]) if DATA["regions"] else "Indonesia"
        event = random.choice(DATA["events"]) if DATA["events"] else "market developments"
        
        # Randomly select a question template
        templates = [
            # Macro economy
            f"What are the latest trends in {topic} and what are the implications for Indonesia's economy?",
            f"How is {indicator} performing in {region} and what does it signal for monetary policy?",
            f"What are the key drivers of {topic} and what is the outlook for the coming months?",
            
            # Sectors
            f"What is the current valuation and outlook for the {sector} sector in Indonesia?",
            f"Which companies are leading the {sector} sector and what are their growth prospects?",
            f"What are the key risks and opportunities in the {sector} sector right now?",
            
            # Companies
            f"What are the latest earnings and performance of {company} and what's the investment thesis?",
            f"How is {company} positioned in the current market environment?",
            f"What are the growth prospects for {company} and what are the key catalysts?",
            
            # Commodities
            f"What is the current price and outlook for {commodity} and what's driving the market?",
            f"How will {commodity} prices impact Indonesia's trade balance and economy?",
            f"What are the supply-demand dynamics for {commodity} and what's the price forecast?",
            
            # Global/regional
            f"How are {region} market developments affecting Indonesian stocks and bonds?",
            f"What is the impact of {region}'s policy changes on global markets and Indonesia?",
            f"What are the trade and investment implications of developments in {region}?",
            
            # Policy/regulation
            f"What are the latest policy changes affecting {sector} and what's the market reaction?",
            f"How will new regulations impact {topic} and what should investors watch?",
            
            # Market sentiment
            f"What is the current market sentiment toward {sector} and what's driving it?",
            f"What are the key technical and fundamental indicators for {topic} right now?",
            
            # Investment
            f"What is the recommended investment strategy for {sector} in the current environment?",
            f"Which stocks or sectors are best positioned to benefit from {topic}?",
            f"What are the top investment opportunities in {region} right now?",
            
            # Specific events
            f"What is the market impact of the upcoming {event} and what should investors expect?",
            f"How are markets reacting to recent developments in {topic} and what's next?",
        ]
        
        # Pick a random template
        template = random.choice(templates)
        question = template
        
        # Clean up
        question = question.strip()
        if not question.endswith('?'):
            question += '?'
        
        # Check for duplicates
        existing = get_all_questions()
        if is_duplicate_question(question, existing):
            # Try again with a different template
            template = random.choice(templates)
            question = template.strip()
            if not question.endswith('?'):
                question += '?'
            
            # If still duplicate, return random fallback
            if is_duplicate_question(question, existing):
                return get_random_fallback_question()
        
        logger.info(f"✨ Generated question from data: {question[:60]}...")
        return question
        
    except Exception as e:
        logger.error(f"Error generating question: {e}")
        return get_random_fallback_question()


def is_duplicate_question(new_question: str, existing_questions: List[str], threshold: float = 0.6) -> bool:
    """Check if a question is too similar to existing ones"""
    if not existing_questions:
        return False
    
    # Get important words
    stop_words = {'what', 'is', 'are', 'the', 'of', 'to', 'for', 'on', 'at', 'from', 'by', 'in', 'with', 'and', 'or', 'but', 'nor', 'into', 'through', 'during', 'including', 'without', 'against', 'between', 'among', 'upon', 'about', 'after', 'before', 'under', 'over', 'above', 'below', 'between'}
    
    new_words = set([w.lower() for w in new_question.split() if w.lower() not in stop_words and len(w) > 3])
    
    for existing in existing_questions[-15:]:
        existing_words = set([w.lower() for w in existing.split() if w.lower() not in stop_words and len(w) > 3])
        
        if not new_words or not existing_words:
            continue
        
        overlap = len(new_words.intersection(existing_words)) / len(new_words.union(existing_words))
        
        if overlap > threshold:
            return True
    
    return False


def get_random_fallback_question() -> str:
    """Return a random fallback question"""
    fallbacks = [
        "What is the current Rupiah exchange rate against USD and what are the key drivers?",
        "What is the latest JCI performance and which sectors are leading the market?",
        "What is the current oil price and how does it impact Indonesia's trade balance?",
        "What are the latest earnings from major Indonesian banks and what do they indicate?",
        "What is the current inflation rate and how is BI responding?",
        "What are the latest foreign investment trends in Indonesia?",
        "What is the current state of Indonesia's manufacturing sector?",
        "What are the key risks and opportunities in the Indonesian stock market?",
        "How is Indonesia's digital economy evolving and what are the key players?",
        "What is the outlook for commodity prices and their impact on Indonesia?",
        "What are the latest developments in Indonesia's infrastructure projects?",
        "How is the global economic slowdown affecting Indonesia's economy?",
        "What are the current trends in Indonesian consumer spending?",
        "What is the outlook for Indonesia's sovereign debt and bond yields?",
        "What are the most promising sectors for investment in Indonesia right now?",
        "How is the tech sector performing in Indonesia and what are the growth drivers?",
        "What is the impact of global supply chain disruptions on Indonesia?",
        "What are the latest policy signals from Bank Indonesia and their market impact?",
        "How is the Indonesian property market performing and what are the risks?",
        "What are the key themes driving the Indonesian market this quarter?"
    ]
    
    return random.choice(fallbacks)


def get_default_fallback_questions() -> List[str]:
    """Get a list of fallback questions"""
    return [
        "What is the current Rupiah exchange rate against USD?",
        "What is the latest JCI performance and key movers?",
        "What is the current oil price and its impact on Indonesia?",
        "What are the latest earnings from major Indonesian banks?",
        "What is the current inflation rate and BI's policy response?"
    ]


def get_file_paths() -> dict:
    return {
        "question_file": str(QUESTION_FILE),
        "archive_file": str(ARCHIVE_FILE),
        "question_file_exists": QUESTION_FILE.exists(),
        "archive_file_exists": ARCHIVE_FILE.exists(),
        "project_root": str(PROJECT_ROOT)
    }


def get_data_summary() -> dict:
    return {
        "topics_count": len(DATA["topics"]),
        "sectors_count": len(DATA["sectors"]),
        "companies_count": len(DATA["companies"]),
        "commodities_count": len(DATA["commodities"]),
        "indicators_count": len(DATA["indicators"]),
        "sample_topics": DATA["topics"][:5],
        "sample_sectors": DATA["sectors"][:5]
    }