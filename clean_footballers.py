#!/usr/bin/env python3
"""
Clean footballer data by filtering to only include players who have
represented the England Men's Senior Team (as listed on englandfootball.com).

This script:
1. Scrapes the England Football legacy players list
2. Filters footballers_fbref.csv to only include players on that list
3. Outputs a cleaned CSV file
"""

import csv
import requests
from bs4 import BeautifulSoup
import re
import argparse
from difflib import SequenceMatcher

# Headers for web scraping
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def scrape_england_legacy_players():
    """Scrape the list of England legacy players from englandfootball.com"""
    url = "https://www.englandfootball.com/england/mens-senior-team/Legacy?tab=Players"
    
    print(f"Scraping England legacy players from {url}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        players = []
        seen_names = set()
        
        # Method 1: Look for divs with player names (based on HTML structure)
        # Format: <div>1&nbsp;Robert Barker</div>
        for div in soup.find_all('div'):
            text = div.get_text().strip()
            # Pattern: starts with number, followed by name
            match = re.match(r'^(\d+)\s+(.+?)$', text)
            if match:
                name = match.group(2).strip()
                # Clean up HTML entities and normalize
                name = name.replace('\xa0', ' ').strip()
                name = re.sub(r'\s+', ' ', name)
                
                # Validate it's a person's name
                if (len(name) > 2 and 
                    not name.isupper() and 
                    len(name.split()) <= 5 and
                    name[0].isupper()):
                    norm_name = normalize_name(name)
                    if norm_name not in seen_names:
                        seen_names.add(norm_name)
                        players.append(name)
        
        # Method 2: Extract from text content (fallback)
        if len(players) < 100:  # If we didn't get many, try text parsing
            content = soup.find('main') or soup.find('body')
            if content:
                text = content.get_text()
                lines = text.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Pattern: number followed by name
                    match = re.match(r'^(\d+)\s+(.+?)(?:\s*$|\s+\d)', line)
                    if match:
                        name = match.group(2).strip()
                        name = re.sub(r'\s+', ' ', name)
                        
                        # Validate
                        if (len(name) > 2 and 
                            not name.isupper() and 
                            len(name.split()) <= 5 and
                            name[0].isupper()):
                            norm_name = normalize_name(name)
                            if norm_name not in seen_names:
                                seen_names.add(norm_name)
                                players.append(name)
        
        # Sort by legacy number (extracted from original order)
        print(f"Found {len(players)} England legacy players")
        return players
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page: {e}")
        return []
    except Exception as e:
        print(f"Error parsing page: {e}")
        import traceback
        traceback.print_exc()
        return []

def normalize_name(name):
    """Normalize a name for comparison (lowercase, remove extra spaces, handle common variations)"""
    if not name:
        return ""
    
    # Convert to lowercase
    name = name.lower().strip()
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name)
    
    # Remove common prefixes/suffixes that might differ
    # Remove periods after initials
    name = re.sub(r'\.', '', name)
    
    # Handle apostrophes and quotes (e.g., "A'Court" vs "A Court")
    name = re.sub(r"[''`]", '', name)
    
    # Remove common prefixes
    name = re.sub(r'^(rev\.?|dr\.?|canon\.?|prof\.?)\s+', '', name, flags=re.IGNORECASE)
    
    return name

def name_similarity(name1, name2):
    """Calculate similarity between two names (0.0 to 1.0)"""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    # Exact match
    if norm1 == norm2:
        return 1.0
    
    # Use SequenceMatcher for fuzzy matching
    return SequenceMatcher(None, norm1, norm2).ratio()

def match_player_name(footballer_name, england_players, threshold=0.80):
    """Try to match a footballer name to an England legacy player"""
    footballer_norm = normalize_name(footballer_name)
    
    # First try exact match
    for england_name in england_players:
        if normalize_name(england_name) == footballer_norm:
            return england_name
    
    # Try matching last name + first name (handle middle names/initials)
    footballer_words = footballer_norm.split()
    if len(footballer_words) >= 2:
        footballer_last = footballer_words[-1]
        footballer_first = footballer_words[0]
        
        for england_name in england_players:
            england_norm = normalize_name(england_name)
            england_words = england_norm.split()
            if len(england_words) >= 2:
                england_last = england_words[-1]
                england_first = england_words[0]
                
                # Match if last name matches and first name matches (or first initial matches)
                if (england_last == footballer_last and 
                    (england_first == footballer_first or 
                     england_first[0] == footballer_first[0] or
                     footballer_first[0] == england_first[0])):
                    return england_name
    
    # Then try fuzzy matching
    best_match = None
    best_score = 0.0
    
    for england_name in england_players:
        score = name_similarity(footballer_name, england_name)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = england_name
    
    return best_match

def clean_footballers(input_file, output_file, england_players):
    """Filter footballer data to only include England legacy players"""
    
    print(f"\nReading {input_file}...")
    footballers = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        footballers = list(reader)
    
    print(f"Found {len(footballers)} footballers in input file")
    
    # Match footballers to England legacy players
    matched_footballers = []
    unmatched_names = []
    
    print(f"\nMatching footballers to England legacy players...")
    for footballer in footballers:
        name = footballer.get('Name', '').strip()
        if not name:
            continue
        
        match = match_player_name(name, england_players, threshold=0.85)
        if match:
            matched_footballers.append(footballer)
        else:
            unmatched_names.append(name)
    
    print(f"\nMatched {len(matched_footballers)} footballers to England legacy players")
    print(f"Unmatched: {len(unmatched_names)} footballers")
    
    # Write matched footballers to output file
    if matched_footballers:
        print(f"\nWriting {len(matched_footballers)} matched footballers to {output_file}...")
        
        fieldnames = list(matched_footballers[0].keys())
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(matched_footballers)
        
        print(f"✓ Saved {len(matched_footballers)} footballers to {output_file}")
        
        # Print statistics
        print("\nStatistics:")
        print(f"  Total England legacy players found: {len(england_players)}")
        print(f"  Footballers matched: {len(matched_footballers)}")
        print(f"  Match rate: {len(matched_footballers) / len(england_players) * 100:.1f}%")
        
        # Show some unmatched names for debugging
        if unmatched_names and len(unmatched_names) <= 20:
            print(f"\nSample unmatched names (first 10):")
            for name in unmatched_names[:10]:
                print(f"  - {name}")
    else:
        print("No matched footballers found. Check the matching logic.")
    
    return matched_footballers

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Filter footballers to only include England legacy players')
    parser.add_argument('input_file', help='Input CSV file with footballer data (e.g., data/footballers_fbref.csv)')
    parser.add_argument('output_file', help='Output CSV file for cleaned data (e.g., data/footballers_cleaned.csv)')
    parser.add_argument('--threshold', type=float, default=0.85,
                       help='Name matching similarity threshold (0.0-1.0, default: 0.85)')
    
    args = parser.parse_args()
    
    # Scrape England legacy players
    england_players = scrape_england_legacy_players()
    
    if not england_players:
        print("Error: Could not scrape England legacy players. Exiting.")
        exit(1)
    
    # Clean and filter footballers
    clean_footballers(args.input_file, args.output_file, england_players)

