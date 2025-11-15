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

def extract_birthplace(soup):
    """Extract birthplace from Wikipedia infobox"""
    try:
        infobox = soup.find('table', class_='infobox')
        if not infobox:
            return None
        
        # Look for "Born" row in infobox
        for row in infobox.find_all('tr'):
            th = row.find('th')
            if th and 'born' in th.get_text().lower():
                td = row.find('td')
                if td:
                    # Get the text, which often contains birthplace
                    # First, try to find links to places (more reliable)
                    place_links = td.find_all('a', href=True)
                    place_names = []
                    for link in place_links:
                        href = link.get('href', '')
                        # Look for links that might be places (not person pages, categories, etc.)
                        if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
                            link_text = link.get_text().strip()
                            # Skip if it's clearly not a place (e.g., person names, dates)
                            if (len(link_text) > 2 and 
                                not link_text.isdigit() and
                                not re.match(r'^\d{1,2}\s+\w+', link_text)):  # Not a date
                                place_names.append(link_text)
                    
                    if place_names:
                        # Usually the last link is the most specific (city, country)
                        # Or combine them if there are multiple
                        if len(place_names) >= 2:
                            return f"{place_names[-2]}, {place_names[-1]}"
                        else:
                            return place_names[-1]
                    
                    # Fallback: extract from text
                    text = td.get_text()
                    # Remove birth date if present (e.g., "1 January 1970" or "January 1, 1970")
                    text = re.sub(r'\d{1,2}\s+\w+\s+\d{4}', '', text)
                    text = re.sub(r'\w+\s+\d{1,2},?\s+\d{4}', '', text)
                    text = re.sub(r'\d{4}', '', text)  # Remove standalone years
                    
                    # Clean up the text
                    text = text.strip()
                    # Remove common prefixes
                    text = re.sub(r'^in\s+', '', text, flags=re.IGNORECASE)
                    text = text.strip()
                    
                    # Extract location (take first part before comma or parentheses)
                    if ',' in text:
                        parts = [p.strip() for p in text.split(',')]
                        # Take the first part (city) and last part (country)
                        if len(parts) >= 2:
                            city = parts[0].strip()
                            country = parts[-1].strip()
                            # Remove any parenthetical info
                            city = re.sub(r'\([^)]*\)', '', city).strip()
                            country = re.sub(r'\([^)]*\)', '', country).strip()
                            if city and country:
                                return f"{city}, {country}"
                            elif city:
                                return city
                        else:
                            return parts[0].strip() if parts else None
                    elif '(' in text:
                        # Extract text before parentheses
                        location = text.split('(')[0].strip()
                        return location if location else None
                    else:
                        return text.strip() if text else None
        
        return None
    except Exception as e:
        print(f"    Error extracting birthplace: {e}")
        return None

def geocode_location(location):
    """Geocode a location name to coordinates"""
    if not location:
        return None
    
    try:
        geolocator = Nominatim(user_agent="EndTeddingtonNowBot/1.0")
        # Add a small delay to respect rate limits
        time.sleep(1)
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
    
    # Get birthplace and distance
    print(f"  Getting birthplace...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
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
        time.sleep(0.5)
        
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

