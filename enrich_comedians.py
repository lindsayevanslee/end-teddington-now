#!/usr/bin/env python3
"""
Enrich comedian data with additional information from Wikipedia pages:
- Page length (character count)
- Age (calculated from birth/death year)
- Distance of birthplace from Teddington, UK
"""

import requests
from bs4 import BeautifulSoup
import csv
import pandas as pd
from datetime import date
import time
import re
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import sys
import argparse

# Teddington, UK coordinates
TEDDINGTON_LAT = 51.4244
TEDDINGTON_LON = -0.3306
TEDDINGTON_COORDS = (TEDDINGTON_LAT, TEDDINGTON_LON)

# Wikipedia User-Agent header
HEADERS = {
    'User-Agent': 'EndTeddingtonNowBot/1.0 (https://endteddingtonnow.com; web scraping for comedy purposes)'
}

def get_page_length(url):
    """Get the length of a Wikipedia page in characters"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the main content area
        content = soup.find('div', {'id': 'mw-content-text'})
        if not content:
            return None
        
        # Get all text content, excluding references and navigation
        # Remove script and style elements
        for script in content(["script", "style", "nav", "table"]):
            script.decompose()
        
        # Get text and count characters
        text = content.get_text()
        return len(text)
    except Exception as e:
        print(f"    Error getting page length: {e}")
        return None

def calculate_age(birth_year, death_year=None):
    """Calculate age from birth year and optional death year"""
    if not birth_year or not str(birth_year).strip():
        return None
    
    try:
        birth_year = int(birth_year)
        if death_year and str(death_year).strip():
            # Deceased - use death year
            death_year = int(death_year)
            return death_year - birth_year
        else:
            # Living - use current year
            current_year = date.today().year
            return current_year - birth_year
    except (ValueError, TypeError):
        return None

def extract_location_from_text(text):
    """Extract location from text, looking for place links and location patterns"""
    if not text:
        return None
    
    # Look for common location patterns with better context
    # Pattern: "born in [Location]" or "born [Location]" or "from [Location]"
    # Be more specific to avoid false positives
    patterns = [
        r'born\s+(?:in\s+)?([A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?)(?:\s+on\s+\d|\s+in\s+\d{4}|\.|,|$)',
        r'(?:is|was)\s+born\s+(?:in\s+)?([A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?)(?:\s+on\s+\d|\s+in\s+\d{4}|\.|,|$)',
        r'from\s+([A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?)(?:\s+where|\s+he|\s+she|\.|,|$)',
        r'grew\s+up\s+(?:in\s+)?([A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?)(?:\s+where|\s+before|\.|,|$)',
        r'raised\s+(?:in\s+)?([A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?)(?:\s+where|\s+before|\.|,|$)',
        r'hails\s+from\s+([A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?)(?:\s+where|\.|,|$)',
    ]
    
    # Words that shouldn't be part of a location
    exclude_words = ['gatecrashing', 'prince', 'william', 'duke', 'earl', 'lord', 'lady', 'king', 'queen', 
                     'princess', 'the', 'and', 'or', 'with', 'from', 'in', 'on', 'at', 'to', 'for', 'of']
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            location = match.group(1).strip()
            # Clean up common suffixes
            location = re.sub(r'\s+(?:on|in|at|where|before)\s+.*$', '', location, flags=re.IGNORECASE)
            location = location.rstrip('.,;')
            
            # Filter out locations that contain excluded words (unless it's a proper place name)
            words = location.split()
            if any(word.lower() in exclude_words and word.lower() not in ['the', 'and'] for word in words):
                # Check if it's a known place (like "Prince William County" - but we'll skip for now)
                if 'prince' in location.lower() or 'duke' in location.lower():
                    continue
            
            # Must be meaningful and look like a place name
            if len(location) > 2 and len(location.split()) <= 4:  # Reasonable length
                return location
    
    return None

def extract_location_from_element(elem):
    """Extract location from a BeautifulSoup element, looking for place links"""
    if not elem:
        return None
    
    # Words that are unlikely to be place names
    exclude_words = ['gatecrashing', 'prince', 'william', 'duke', 'earl', 'lord', 'lady', 'king', 'queen',
                     'princess', 'born', 'died', 'married', 'divorced', 'graduated', 'attended', 'worked']
    
    # First, try to find links to places (more reliable)
    # Get ALL links in order - don't limit, capture everything that looks like a place
    place_links = elem.find_all('a', href=True)
    place_names = []
    for link in place_links:
        href = link.get('href', '')
        # Look for links that might be places (not person pages, categories, etc.)
        if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
            link_text = link.get_text().strip()
            
            # Skip if it's clearly not a place
            if (len(link_text) > 2 and 
                not link_text.isdigit() and
                not re.match(r'^\d{1,2}\s+\w+', link_text) and  # Not a date
                link_text.lower() not in ['the', 'and', 'or', 'with', 'from', 'in', 'on', 'at', 'to', 'for', 'of'] and
                not any(word in link_text.lower() for word in exclude_words) and
                # Must start with capital letter (proper noun)
                link_text[0].isupper()):
                place_names.append(link_text)
    
    # Also check for place names in the text that might not be linked
    # This helps capture cases where some parts are linked and others aren't
    # For example: "Southampton, Hampshire, England" where England is not linked
    text = elem.get_text()
    
    if place_names:
        # Filter out any that still look wrong
        valid_places = []
        for name in place_names:
            # Skip if it contains excluded words
            if not any(word in name.lower() for word in exclude_words):
                # Must look like a place name (1-4 words, reasonable length)
                words = name.split()
                if 1 <= len(words) <= 4 and len(name) <= 50:
                    valid_places.append(name)
        
        if valid_places:
            # Now check if there's additional text after the linked places
            # Extract the full location string from the text, preserving commas
            # Remove dates first
            text_clean = re.sub(r'\([^)]*\d{4}[^)]*\)', '', text)  # Remove date in parentheses
            text_clean = re.sub(r'\d{1,2}\s+\w+\s+\d{4}', '', text_clean)  # Remove date patterns
            text_clean = re.sub(r'\d{4}', '', text_clean)  # Remove standalone years
            text_clean = re.sub(r'\(age\s+\d+\)', '', text_clean, flags=re.IGNORECASE)  # Remove age
            
            # Look for the pattern: place1, place2, place3 (where some might not be linked)
            # Find where our linked places appear in the text
            if len(valid_places) > 0:
                # Try to find the full location string in the text
                # Look for patterns like "City, County, Country" or "City, Country"
                # But avoid capturing person names - look for location patterns after dates or common location words
                location_pattern = r'([A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+){0,3})'
                matches = re.findall(location_pattern, text_clean)
                
                # Find the match that contains our linked places
                for match in matches:
                    match_lower = match.lower()
                    # Check if this match contains all our linked places
                    if all(place.lower() in match_lower for place in valid_places):
                        # Filter out if it looks like a person name (has 3+ words and doesn't contain location indicators)
                        words = match.split()
                        if len(words) <= 4:  # Locations are usually 1-4 words
                            # Additional check: if it starts with a common first name, skip it
                            common_first_names = ['adam', 'john', 'david', 'michael', 'james', 'robert', 'william', 
                                                 'richard', 'thomas', 'charles', 'daniel', 'matthew', 'mark', 'paul']
                            if words[0].lower() not in common_first_names or any(place.lower() in match_lower for place in valid_places):
                                # This is likely the full location - use it
                                return match.strip()
            
            # Fallback: just join the linked places
            return ", ".join(valid_places)
    
    # Fallback: extract from text
    text = elem.get_text()
    location = extract_location_from_text(text)
    if location:
        return location
    
    # Try to extract from text patterns - preserve full location as written
    text = elem.get_text()
    # Remove birth date if present
    text = re.sub(r'\d{1,2}\s+\w+\s+\d{4}', '', text)
    text = re.sub(r'\w+\s+\d{1,2},?\s+\d{4}', '', text)
    text = re.sub(r'\d{4}', '', text)
    
    # Clean up the text
    text = text.strip()
    text = re.sub(r'^in\s+', '', text, flags=re.IGNORECASE)
    text = text.strip()
    
    # Extract location - preserve all parts separated by commas
    if ',' in text:
        parts = [p.strip() for p in text.split(',')]
        # Remove parenthetical info but keep all location parts
        cleaned_parts = []
        for part in parts:
            # Remove parenthetical info from each part
            cleaned = re.sub(r'\([^)]*\)', '', part).strip()
            if cleaned:
                cleaned_parts.append(cleaned)
        if cleaned_parts:
            # Return all parts joined - this preserves the full location
            return ", ".join(cleaned_parts)
    elif '(' in text:
        # Extract text before parentheses, but keep everything else
        location = text.split('(')[0].strip()
        return location if location else None
    else:
        return text.strip() if text else None

def extract_birthplace(soup):
    """Extract birthplace from Wikipedia infobox, or from article text if not found"""
    try:
        # Method 1: Try infobox first
        infobox = soup.find('table', class_='infobox')
        if infobox:
            # Look for "Born" row in infobox
            for row in infobox.find_all('tr'):
                th = row.find('th')
                if th and 'born' in th.get_text().lower():
                    td = row.find('td')
                    if td:
                        location = extract_location_from_element(td)
                        if location:
                            return location
        
        # Method 2: Search article text in relevant sections
        content = soup.find('div', {'id': 'mw-content-text'})
        if not content:
            return None
        
        # Look for relevant section headings
        section_keywords = ['early life', 'background', 'personal life', 'biography', 'life and career']
        
        for heading in content.find_all(['h2', 'h3']):
            heading_text = heading.get_text().lower()
            # Remove [edit] markers
            heading_text = re.sub(r'\[.*?\]', '', heading_text).strip()
            
            # Check if this is a relevant section
            if any(keyword in heading_text for keyword in section_keywords):
                # Get the content of this section (up to next heading)
                section_content = []
                current = heading.find_next_sibling()
                
                # Collect paragraphs and lists until next heading
                while current and current.name not in ['h2', 'h3']:
                    if current.name == 'p':
                        section_content.append(current)
                    elif current.name in ['ul', 'ol']:
                        # Check list items too
                        for li in current.find_all('li', limit=3):  # First few items
                            section_content.append(li)
                    current = current.find_next_sibling()
                
                # Search through section content for location indicators
                for elem in section_content[:5]:  # Check first 5 elements
                    # First, try to extract from links (most reliable)
                    link_location = extract_location_from_element(elem)
                    if link_location:
                        # Validate it looks like a place name
                        if len(link_location.split()) <= 4 and len(link_location) > 2:
                            return link_location
                    
                    # Then try text patterns
                    text = elem.get_text()
                    location = extract_location_from_text(text)
                    if location:
                        return location
        
        # Method 3: Check first paragraph as fallback
        first_p = content.find('p')
        if first_p:
            location = extract_location_from_element(first_p)
            if location:
                return location
        
        return None
    except Exception as e:
        print(f"    Error extracting birthplace: {e}")
        return None

def geocode_location(location):
    """Geocode a location name to coordinates - use location as written"""
    if not location:
        return None
    
    try:
        geolocator = Nominatim(user_agent="EndTeddingtonNowBot/1.0")
        # Add a small delay to respect rate limits
        time.sleep(1)
        
        # Geocode the location exactly as written - don't modify it
        location_obj = geolocator.geocode(location, timeout=10)
        
        if location_obj:
            return (location_obj.latitude, location_obj.longitude)
        
        return None
    except Exception as e:
        print(f"    Error geocoding {location}: {e}")
        return None

def calculate_distance(coords):
    """Calculate distance in kilometers from Teddington to given coordinates"""
    if not coords:
        return None
    
    try:
        distance = geodesic(TEDDINGTON_COORDS, coords).kilometers
        return round(distance, 2)
    except Exception as e:
        print(f"    Error calculating distance: {e}")
        return None

def extract_gender(soup):
    """Extract gender from pronouns used in the Wikipedia article"""
    try:
        # Look for pronoun patterns in the article
        # Check first few paragraphs and infobox
        
        content = soup.find('div', {'id': 'mw-content-text'})
        if not content:
            return None
        
        # Get first few paragraphs (most reliable for biographical info)
        paragraphs = content.find_all('p', limit=5)
        
        # Also check infobox
        infobox = soup.find('table', class_='infobox')
        infobox_text = ""
        if infobox:
            infobox_text = infobox.get_text()
        
        # Combine text from paragraphs and infobox
        text_to_check = infobox_text + " " + " ".join([p.get_text() for p in paragraphs])
        text_lower = text_to_check.lower()
        
        # Count pronoun occurrences
        male_pronouns = [' he ', ' his ', ' him ', ' himself ']
        female_pronouns = [' she ', ' her ', ' hers ', ' herself ']
        
        male_count = sum(text_lower.count(pronoun) for pronoun in male_pronouns)
        female_count = sum(text_lower.count(pronoun) for pronoun in female_pronouns)
        
        # Also check for "he is", "she is" patterns (more reliable)
        male_patterns = [r'\bhe\s+is\b', r'\bhis\s+\w+', r'\bhim\s+to\b']
        female_patterns = [r'\bshe\s+is\b', r'\bher\s+\w+', r'\bher\s+to\b']
        
        for pattern in male_patterns:
            if re.search(pattern, text_lower):
                male_count += 2  # Weight these more heavily
        
        for pattern in female_patterns:
            if re.search(pattern, text_lower):
                female_count += 2  # Weight these more heavily
        
        # Determine gender based on pronoun usage
        # Need a clear majority to be confident
        if female_count > male_count and female_count >= 2:
            return 'Female'
        elif male_count > female_count and male_count >= 2:
            return 'Male'
        else:
            # Not enough evidence or ambiguous
            return None
            
    except Exception as e:
        print(f"    Error extracting gender: {e}")
        return None

def enrich_comedian(row, geolocator_cache=None):
    """Enrich a single comedian's data"""
    name = row['Name']
    url = row['URL']
    
    # Handle NaN values from pandas
    birth_year = row.get('BirthYear', '')
    if pd.isna(birth_year):
        birth_year = ''
    else:
        # Convert to int first to remove .0, then to string
        try:
            birth_year = str(int(float(birth_year)))
        except (ValueError, TypeError):
            birth_year = str(birth_year).strip()
    
    death_year = row.get('DeathYear', '')
    if pd.isna(death_year):
        death_year = ''
    else:
        # Convert to int first to remove .0, then to string
        try:
            death_year = str(int(float(death_year)))
        except (ValueError, TypeError):
            death_year = str(death_year).strip()
    
    print(f"Processing: {name}")
    
    result = {
        'Name': name,
        'URL': url,
        'Type': row.get('Type', ''),
        'BirthYear': birth_year,
        'DeathYear': death_year,
        'PageLength': None,
        'Age': None,
        'Gender': None,
        'Birthplace': None,
        'BirthplaceLat': None,
        'BirthplaceLon': None,
        'DistanceFromTeddington': None
    }
    
    if not url or not url.strip():
        print(f"  No URL, skipping")
        return result
    
    # Get page length
    print(f"  Getting page length...")
    page_length = get_page_length(url)
    result['PageLength'] = page_length
    
    # Calculate age
    age = calculate_age(birth_year, death_year)
    result['Age'] = age
    if age:
        print(f"  Age: {age}")
    
    # Get birthplace, distance, and gender
    print(f"  Getting birthplace and gender...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract gender from pronouns
        gender = extract_gender(soup)
        result['Gender'] = gender
        if gender:
            print(f"  Gender: {gender}")
        
        birthplace = extract_birthplace(soup)
        result['Birthplace'] = birthplace
        
        if birthplace:
            print(f"  Birthplace: {birthplace}")
            
            # Geocode birthplace
            print(f"  Geocoding...")
            coords = geocode_location(birthplace)
            
            if coords:
                result['BirthplaceLat'] = coords[0]
                result['BirthplaceLon'] = coords[1]
                
                # Calculate distance
                distance = calculate_distance(coords)
                result['DistanceFromTeddington'] = distance
                if distance:
                    print(f"  Distance from Teddington: {distance} km")
            else:
                print(f"  Could not geocode birthplace")
        else:
            print(f"  Could not find birthplace")
    except Exception as e:
        print(f"  Error processing page: {e}")
    
    return result

def enrich_comedians(input_file, output_file, limit=None):
    """Enrich all comedians in the input CSV file
    
    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV file
        limit: Optional limit on number of rows to process (for testing)
    """
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    
    # Limit rows if specified
    if limit:
        df = df.head(limit)
        print(f"Limited to first {limit} rows for testing")
    
    print(f"Processing {len(df)} comedians")
    print(f"Starting enrichment (this may take a while)...\n")
    
    enriched_data = []
    
    for idx, row in df.iterrows():
        enriched = enrich_comedian(row)
        enriched_data.append(enriched)
        
        # Add a small delay between requests to be respectful
        time.sleep(0.2)
        
        # Progress update every 10 comedians
        if (idx + 1) % 10 == 0:
            print(f"\nProgress: {idx + 1}/{len(df)} comedians processed\n")
    
    # Save to CSV
    print(f"\nSaving enriched data to {output_file}...")
    df_enriched = pd.DataFrame(enriched_data)
    df_enriched.to_csv(output_file, index=False)
    
    print(f"Done! Saved {len(enriched_data)} enriched entries to {output_file}")
    
    # Print statistics
    print("\nStatistics:")
    print(f"  Total comedians: {len(enriched_data)}")
    print(f"  With page length: {sum(1 for e in enriched_data if e['PageLength'] is not None)}")
    print(f"  With age: {sum(1 for e in enriched_data if e['Age'] is not None)}")
    print(f"  With gender: {sum(1 for e in enriched_data if e['Gender'] is not None)}")
    print(f"  With birthplace: {sum(1 for e in enriched_data if e['Birthplace'] is not None)}")
    print(f"  With distance: {sum(1 for e in enriched_data if e['DistanceFromTeddington'] is not None)}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Enrich comedian data with Wikipedia page information',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all comedians
  python enrich_comedians.py
  
  # Process first 10 comedians (for testing)
  python enrich_comedians.py --limit 10
  
  # Process first 5 with custom input/output files
  python enrich_comedians.py input.csv output.csv --limit 5
        """
    )
    
    parser.add_argument(
        'input_file',
        nargs='?',
        default='data/comedians_cleaned.csv',
        help='Input CSV file (default: data/comedians_cleaned.csv)'
    )
    
    parser.add_argument(
        'output_file',
        nargs='?',
        default='data/comedians_enriched.csv',
        help='Output CSV file (default: data/comedians_enriched.csv)'
    )
    
    parser.add_argument(
        '--limit', '-n',
        type=int,
        default=None,
        help='Limit processing to first N rows (useful for testing)'
    )
    
    args = parser.parse_args()
    
    enrich_comedians(args.input_file, args.output_file, limit=args.limit)

