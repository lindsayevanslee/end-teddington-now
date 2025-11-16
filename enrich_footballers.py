#!/usr/bin/env python3
"""
Enrich footballer data by scraping individual player pages from fbref.com.
Extracts additional metadata from each player's page.

Note: fbref.com (sports-reference.com) has a rate limit of 10 requests per minute.
This script uses a 6-second delay between requests to comply with this limit.
See: https://www.sports-reference.com/bot-traffic.html
"""

import csv
import requests
import time
import re
import argparse
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import date

# Teddington, UK coordinates
TEDDINGTON_LAT = 51.4244
TEDDINGTON_LON = -0.3306
TEDDINGTON_COORDS = (TEDDINGTON_LAT, TEDDINGTON_LON)

def extract_player_data_from_page(url, driver=None):
    """Extract player metadata from a fbref.com player page"""
    try:
        # Use Selenium if driver is provided, otherwise try requests
        if driver:
            driver.get(url)
            # Wait for page to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(2)  # Additional wait for content
                page_source = driver.page_source
            except:
                page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
        else:
            # Fallback to requests (may not work due to Cloudflare)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
        player_data = {}
        
        # First, try to extract structured data from JSON-LD schema
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Person':
                    # Extract structured data
                    if 'name' in data and not player_data.get('Full_Name'):
                        player_data['Full_Name'] = data['name']
                    if 'birthPlace' in data and not player_data.get('Birthplace'):
                        player_data['Birthplace'] = data['birthPlace']
                    if 'height' in data:
                        height_obj = data['height']
                        if isinstance(height_obj, dict) and 'value' in height_obj:
                            if not player_data.get('Height'):
                                player_data['Height'] = height_obj['value']
                    if 'weight' in data:
                        weight_obj = data['weight']
                        if isinstance(weight_obj, dict) and 'value' in weight_obj:
                            if not player_data.get('Weight'):
                                player_data['Weight'] = weight_obj['value']
            except (json.JSONDecodeError, AttributeError):
                continue
        
        # Extract player name from the page title or h1
        title = soup.find('h1', class_='nontoc')
        if title:
            player_data['Scraped_Name'] = title.get_text().strip()
        
        # fbref.com uses a specific structure - look for the info div
        info_div = soup.find('div', id='info')
        if not info_div:
            # Try alternative selectors
            info_div = soup.find('div', class_='info') or soup.find('div', {'id': 'meta'})
        
        if info_div:
            # Get all text from info div to parse
            info_text = info_div.get_text()
            
            # Extract full name (often appears after the display name)
            # Look for pattern: "Display Name\nFull Name" or in separate paragraph
            paragraphs = info_div.find_all('p', limit=10)
            for i, p in enumerate(paragraphs):
                text = p.get_text().strip()
                
                # First paragraph after title often contains full name
                if i == 0 and text and len(text) > 3 and not any(word in text.lower() for word in ['position', 'born', 'height', 'weight']):
                    # This might be the full name
                    if not player_data.get('Full_Name'):
                        player_data['Full_Name'] = text
            
            # Extract position: "Position: GK" or "Position: DF"
            position_match = re.search(r'position[:\s]+([A-Z]{1,3}(?:\s*[,\-]\s*[A-Z]{1,3})*)', info_text, re.IGNORECASE)
            if position_match and not player_data.get('Position_Detailed'):
                player_data['Position_Detailed'] = position_match.group(1).strip()
            
            # Extract height and weight: "185cm, 76kg (6-1, 168lb)" or similar
            # Pattern: "XXXcm, XXkg" or "X-X, XXXlb"
            hw_match = re.search(r'(\d+cm)[,\s]+(\d+kg)\s*\(([^)]+)\)', info_text, re.IGNORECASE)
            if hw_match:
                if not player_data.get('Height'):
                    player_data['Height'] = hw_match.group(1)  # e.g., "185cm"
                if not player_data.get('Weight'):
                    player_data['Weight'] = hw_match.group(2)  # e.g., "76kg"
                # Also capture imperial measurements
                imperial = hw_match.group(3).strip()  # e.g., "6-1, 168lb"
                if not player_data.get('Height_Imperial'):
                    player_data['Height_Imperial'] = imperial.split(',')[0].strip() if ',' in imperial else imperial
                if not player_data.get('Weight_Imperial'):
                    weight_imperial = imperial.split(',')[1].strip() if ',' in imperial else ''
                    if 'lb' in weight_imperial.lower():
                        player_data['Weight_Imperial'] = weight_imperial
            else:
                # Try separate patterns
                height_match = re.search(r'(\d+cm|\d+\.\d+m|\d+\s*ft\s*\d+\s*in)', info_text, re.IGNORECASE)
                if height_match and not player_data.get('Height'):
                    player_data['Height'] = height_match.group(1)
                
                weight_match = re.search(r'(\d+kg|\d+\s*lbs?|\d+\s*lb)', info_text, re.IGNORECASE)
                if weight_match and not player_data.get('Weight'):
                    player_data['Weight'] = weight_match.group(1)
            
            # Extract birth date: "Born: July 11, 1978" or "Born:\nJuly 11, 1978"
            # Look in paragraphs first
            for p in paragraphs:
                text = p.get_text()
                if 'born' in text.lower():
                    # Try various date patterns
                    date_patterns = [
                        r'born[:\s]+(\w+\s+\d{1,2},?\s+\d{4})',  # "Born: July 11, 1978" or "Born July 11 1978"
                        r'born[:\s]+(\d{1,2}\s+\w+\s+\d{4})',  # "Born: 11 July 1978"
                        r'born[:\s]+(\d{4})',  # "Born: 1978"
                    ]
                    for pattern in date_patterns:
                        date_match = re.search(pattern, text, re.IGNORECASE)
                        if date_match and not player_data.get('BirthDate'):
                            player_data['BirthDate'] = date_match.group(1).strip()
                            break
            
            # If not found in paragraphs, search the whole info text
            if not player_data.get('BirthDate'):
                date_patterns = [
                    r'born[:\s]+(\w+\s+\d{1,2},?\s+\d{4})',
                    r'born[:\s]+(\d{1,2}\s+\w+\s+\d{4})',
                    r'born[:\s]+(\d{4})',
                ]
                for pattern in date_patterns:
                    date_match = re.search(pattern, info_text, re.IGNORECASE)
                    if date_match:
                        player_data['BirthDate'] = date_match.group(1).strip()
                        break
            
            # Extract birthplace: "in Islington, England, United Kingdom"
            # Look for "in [place]" after "Born"
            birthplace_match = re.search(r'born[^\.]*?in\s+([A-Z][A-Za-z\s,]+?)(?:\.|$|eng|$|\n)', info_text, re.IGNORECASE | re.DOTALL)
            if birthplace_match:
                birthplace = birthplace_match.group(1).strip()
                # Clean up - remove trailing "eng" or other country codes
                birthplace = re.sub(r'\s+eng\s*$', '', birthplace, flags=re.IGNORECASE)
                # Remove common false positives
                if birthplace.lower() not in ['over', 'the', 'a', 'an', 'his', 'her'] and len(birthplace) > 2:
                    if not player_data.get('Birthplace'):
                        player_data['Birthplace'] = birthplace
            
            # Extract citizenship: "Citizenship: England eng"
            citizenship_match = re.search(r'citizenship[:\s]+([^\.\n]+?)(?:\.|$|\n)', info_text, re.IGNORECASE)
            if citizenship_match:
                citizenship = citizenship_match.group(1).strip()
                # Clean up country codes
                citizenship = re.sub(r'\s+[a-z]{2,3}\s*$', '', citizenship, flags=re.IGNORECASE)
                if citizenship:
                    player_data['Citizenship'] = citizenship
        
        # Also check for infobox table (some pages might have this)
        infobox = soup.find('table', class_='infobox')
        if infobox:
            rows = infobox.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                
                if th and td:
                    label = th.get_text().strip().lower()
                    value = td.get_text().strip()
                    
                    # Map common labels to our field names
                    if 'date of birth' in label or ('born' in label and not player_data.get('BirthDate')):
                        date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', value)
                        if date_match:
                            player_data['BirthDate'] = date_match.group(1)
                        elif value:
                            player_data['BirthDate'] = value
                    elif 'place of birth' in label or 'birthplace' in label:
                        if value and value.lower() not in ['over', 'the']:
                            player_data['Birthplace'] = value
                    elif 'height' in label and not player_data.get('Height'):
                        player_data['Height'] = value
                    elif 'weight' in label and not player_data.get('Weight'):
                        player_data['Weight'] = value
                    elif 'position' in label and not player_data.get('Position_Detailed'):
                        player_data['Position_Detailed'] = value
                    elif 'foot' in label or 'footed' in label:
                        player_data['Foot'] = value
                    elif 'current team' in label or 'club' in label:
                        player_data['Current_Team'] = value
                    elif 'nationality' in label or 'country' in label:
                        player_data['Nationality'] = value
        
        # Also check the meta div for structured data
        meta_div = soup.find('div', id='meta')
        if meta_div:
            # fbref.com often has structured data in paragraphs
            meta_paragraphs = meta_div.find_all('p', limit=5)
            for p in meta_paragraphs:
                text = p.get_text()
                
                # Look for birth date: "Born: 4 January 2000" or "Born January 4, 2000"
                if 'born' in text.lower() and not player_data.get('BirthDate'):
                    # Try various date patterns
                    date_patterns = [
                        r'born[:\s]+(\d{1,2}\s+\w+\s+\d{4})',  # "Born: 4 January 2000"
                        r'born[:\s]+(\w+\s+\d{1,2},?\s+\d{4})',  # "Born January 4, 2000"
                        r'born[:\s]+(\d{4})',  # "Born: 2000"
                    ]
                    for pattern in date_patterns:
                        date_match = re.search(pattern, text, re.IGNORECASE)
                        if date_match:
                            player_data['BirthDate'] = date_match.group(1)
                            break
                
                # Look for birthplace: "in [place]" after born
                if 'born' in text.lower() and not player_data.get('Birthplace'):
                    # Pattern: "Born [date] in [place]"
                    place_match = re.search(r'born[^\.]+in\s+([A-Z][A-Za-z\s,]+?)(?:\.|$|,|and|\(|\[)', text, re.IGNORECASE)
                    if place_match:
                        birthplace = place_match.group(1).strip()
                        # Clean up
                        if birthplace.lower() not in ['over', 'the', 'a', 'an', 'his', 'her']:
                            player_data['Birthplace'] = birthplace
        
        # Extract age if available (often in parentheses after name or in infobox)
        age_match = re.search(r'\(age\s+(\d+)\)', soup.get_text(), re.IGNORECASE)
        if age_match:
            player_data['Age'] = age_match.group(1)
        
        # Look for height and weight in the info section more thoroughly
        if not player_data.get('Height') or not player_data.get('Weight'):
            # Search in all paragraphs for height/weight
            all_paragraphs = soup.find_all('p', limit=20)
            for p in all_paragraphs:
                text = p.get_text()
                
                # Height patterns: "Height 1.75 m" or "5 ft 9 in"
                if 'height' in text.lower() and not player_data.get('Height'):
                    height_match = re.search(r'height[:\s]+([^\.\n]+?)(?:\.|$|\n|weight)', text, re.IGNORECASE)
                    if height_match:
                        height = height_match.group(1).strip()
                        if height and len(height) < 50:  # Reasonable length
                            player_data['Height'] = height
                
                # Weight patterns
                if 'weight' in text.lower() and not player_data.get('Weight'):
                    weight_match = re.search(r'weight[:\s]+([^\.\n]+?)(?:\.|$|\n|position|kg|lbs)', text, re.IGNORECASE)
                    if weight_match:
                        weight = weight_match.group(1).strip()
                        if weight and len(weight) < 30:  # Reasonable length
                            player_data['Weight'] = weight
        
        return player_data
        
    except Exception as e:
        print(f"    Error: {e}")
        return {}

def calculate_age(birth_date):
    """Calculate age from birth date string (e.g., 'July 11, 1978' or '1978')"""
    if not birth_date or not str(birth_date).strip():
        return None
    
    try:
        birth_date_str = str(birth_date).strip()
        
        # Try to parse various date formats
        # Format 1: "July 11, 1978" or "11 July 1978"
        date_patterns = [
            r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # "July 11, 1978"
            r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # "11 July 1978"
            r'(\d{4})',  # Just year "1978"
        ]
        
        birth_year = None
        for pattern in date_patterns:
            match = re.search(pattern, birth_date_str)
            if match:
                if len(match.groups()) == 3:
                    # Full date - extract year
                    birth_year = int(match.group(3))
                elif len(match.groups()) == 1:
                    # Just year
                    birth_year = int(match.group(1))
                break
        
        if birth_year:
            current_year = date.today().year
            return current_year - birth_year
        
        return None
    except (ValueError, TypeError, AttributeError):
        return None

def geocode_location(location):
    """Geocode a location string to get coordinates"""
    if not location or not str(location).strip():
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
        print(f"    Geocoding error for '{location}': {e}")
        return None

def calculate_distance(coords):
    """Calculate distance in kilometers from Teddington to given coordinates"""
    if not coords:
        return None
    
    try:
        distance = geodesic(TEDDINGTON_COORDS, coords).kilometers
        return round(distance, 2)
    except Exception as e:
        print(f"    Distance calculation error: {e}")
        return None

def enrich_footballer(row, driver, delay=6):
    """Enrich a single footballer row by scraping their page"""
    url = row.get('URL', '')
    name = row.get('Name', 'Unknown')
    
    if not url:
        print(f"  {name}: No URL found")
        return row
    
    print(f"  {name}...", end=' ', flush=True)
    
    # Scrape the player's page
    player_data = extract_player_data_from_page(url, driver=driver)
    
    if player_data:
        print("✓")
        # Merge scraped data into the row
        enriched_row = row.copy()
        for key, value in player_data.items():
            enriched_row[f'Scraped_{key}'] = value
        
        # Calculate age from birth date
        birth_date = player_data.get('BirthDate')
        if birth_date:
            age = calculate_age(birth_date)
            if age is not None:
                enriched_row['Scraped_Age'] = age
        
        # Calculate distance from Teddington if birthplace is available
        birthplace = player_data.get('Birthplace')
        if birthplace:
            coords = geocode_location(birthplace)
            if coords:
                distance = calculate_distance(coords)
                if distance is not None:
                    enriched_row['Scraped_DistanceFromTeddington'] = distance
        
        return enriched_row
    else:
        print("✗")
        return row

def enrich_footballers(input_file, output_file, limit=None, delay=6):
    """Enrich footballer data by scraping individual pages"""
    
    # Set up Selenium driver to bypass Cloudflare
    print("Setting up browser...")
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        # Remove webdriver property
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        print("Please ensure Chrome/Chromium is installed.")
        return
    
    try:
        print(f"\nReading {input_file}...")
        footballers = []
        
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            footballers = list(reader)
        
        print(f"Found {len(footballers)} footballers")
        
        if limit:
            footballers = footballers[:limit]
            print(f"Processing first {limit} footballers for testing...")
        
        # Enrich each footballer
        enriched_footballers = []
        total = len(footballers)
        
        print(f"\nEnriching {total} footballers by scraping their pages...")
        print(f"This will take approximately {total * delay / 60:.1f} minutes (using {delay} second delay between requests)")
        print(f"Note: fbref.com rate limit is 10 requests/minute, so {delay} seconds ensures compliance\n")
        
        for i, footballer in enumerate(footballers, 1):
            print(f"[{i}/{total}]", end=' ')
            enriched = enrich_footballer(footballer, driver, delay=delay)
            enriched_footballers.append(enriched)
            
            # Rate limiting: wait between requests (except for the last one)
            if i < total:
                time.sleep(delay)
    finally:
        driver.quit()
        print("\nBrowser closed.")
    
    # Write enriched data to output file
    print(f"\nWriting enriched data to {output_file}...")
    
    if enriched_footballers:
        # Get all fieldnames from all enriched footballers (some may have different fields)
        all_fieldnames = set()
        for footballer in enriched_footballers:
            all_fieldnames.update(footballer.keys())
        
        # Sort fieldnames: original fields first, then scraped fields
        original_fields = ['Name', 'URL', 'YearStarted', 'YearEnded', 'Position', 'SquadHistory', 'IsActive']
        scraped_fields = sorted([f for f in all_fieldnames if f.startswith('Scraped_')])
        other_fields = sorted([f for f in all_fieldnames if f not in original_fields and not f.startswith('Scraped_')])
        fieldnames = [f for f in original_fields if f in all_fieldnames] + scraped_fields + other_fields
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched_footballers)
        
        print(f"Saved {len(enriched_footballers)} enriched footballers to {output_file}")
        
        # Print statistics
        print("\nStatistics:")
        print(f"  Total footballers: {len(enriched_footballers)}")
        
        # Count how many have scraped data
        with_birthdate = sum(1 for f in enriched_footballers if f.get('Scraped_BirthDate'))
        with_birthplace = sum(1 for f in enriched_footballers if f.get('Scraped_Birthplace'))
        with_height = sum(1 for f in enriched_footballers if f.get('Scraped_Height'))
        with_weight = sum(1 for f in enriched_footballers if f.get('Scraped_Weight'))
        with_age = sum(1 for f in enriched_footballers if f.get('Scraped_Age'))
        with_distance = sum(1 for f in enriched_footballers if f.get('Scraped_DistanceFromTeddington'))
        
        print(f"  With birth date: {with_birthdate}")
        print(f"  With birthplace: {with_birthplace}")
        print(f"  With height: {with_height}")
        print(f"  With weight: {with_weight}")
        print(f"  With age: {with_age}")
        print(f"  With distance from Teddington: {with_distance}")
        
        # Show sample of enriched data
        print("\nFirst 3 enriched entries:")
        for i, footballer in enumerate(enriched_footballers[:3], 1):
            print(f"  {i}. {footballer.get('Name', 'Unknown')}")
            if footballer.get('Scraped_BirthDate'):
                print(f"     Birth Date: {footballer.get('Scraped_BirthDate')}")
            if footballer.get('Scraped_Birthplace'):
                print(f"     Birthplace: {footballer.get('Scraped_Birthplace')}")
            if footballer.get('Scraped_Height'):
                print(f"     Height: {footballer.get('Scraped_Height')}")
            if footballer.get('Scraped_Age'):
                print(f"     Age: {footballer.get('Scraped_Age')}")
            if footballer.get('Scraped_DistanceFromTeddington'):
                print(f"     Distance from Teddington: {footballer.get('Scraped_DistanceFromTeddington')} km")
    else:
        print("No data to save.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enrich footballer data by scraping fbref.com pages')
    parser.add_argument('input_file', help='Input CSV file with footballer data')
    parser.add_argument('output_file', help='Output CSV file for enriched data')
    parser.add_argument('-n', '--limit', type=int, help='Process only first N rows for testing')
    parser.add_argument('--delay', type=int, default=6, 
                       help='Delay between requests in seconds (default: 6, recommended minimum: 6 to avoid being blocked)')
    
    args = parser.parse_args()
    
    # Ensure delay meets fbref.com rate limit (10 requests/minute = 6 seconds minimum)
    if args.delay < 6:
        print(f"Warning: Delay is less than 6 seconds. Setting to 6 seconds to comply with fbref.com rate limit (10 requests/minute).")
        args.delay = 6
    
    enrich_footballers(
        args.input_file,
        args.output_file,
        limit=args.limit,
        delay=args.delay
    )

