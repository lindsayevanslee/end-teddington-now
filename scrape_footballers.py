#!/usr/bin/env python3
"""
Scrape English footballers from fbref.com HTML file and create a CSV file.

Requires the site https://fbref.com/en/country/players/ENG/England-Football-Players 
to be manually downloaded and saved as data/fbref.html
"""

from bs4 import BeautifulSoup, Comment
import csv
import re


def scrape_from_html_file(html_file):
    """Alternative: Scrape from a manually saved HTML file"""
    print(f"Reading from HTML file: {html_file}")
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    return parse_footballers_from_soup(soup)

def parse_footballers_from_soup(soup):
    """Parse footballer data from BeautifulSoup object"""
    footballers = []
    
    print("\nLooking for player data in section_content divs...")
    
    # Find all divs with class "section_content"
    section_contents = soup.find_all('div', class_='section_content')
    print(f"Found {len(section_contents)} divs with class 'section_content'")
    
    if not section_contents:
        print("Warning: Could not find section_content divs")
        return footballers
    
    # Process each section_content div
    for section_idx, section in enumerate(section_contents):
        # Find all <p> elements in this section
        paragraphs = section.find_all('p')
        print(f"Section {section_idx + 1}: Found {len(paragraphs)} <p> elements")
        
        if not paragraphs:
            continue
        
        # Process each paragraph (each should be a player entry)
        for p in paragraphs:
            text = p.get_text().strip()
            
            # Skip empty paragraphs or the header paragraph
            if not text or 'Years Played' in text:
                continue
            
            # Extract player name from link
            name_link = p.find('a', href=lambda x: x and '/en/players/' in x)
            if not name_link:
                # Skip if no player link found
                continue
            
            name = name_link.get_text().strip()
            player_url = name_link.get('href', '')
            if player_url and not player_url.startswith('http'):
                player_url = f"https://fbref.com{player_url}"
            
            if not name:
                continue
            
            # Check if player name or any text is bold (indicates active player)
            is_active = False
            bold_elem = p.find('strong') or p.find('b')
            if bold_elem:
                bold_text = bold_elem.get_text().strip()
                # If the bold text is the player name or part of the text, they're active
                if bold_text and (name.lower() in bold_text.lower() or bold_text.lower() in name.lower()):
                    is_active = True
                # Also check if bold text appears in the main text (not just the name)
                elif bold_text and bold_text in text:
                    is_active = True
            
            # Extract years played, position, and squad history
            # The format is: Years Played · Position · Squad History
            years_played = ''
            position = ''
            squad_history = ''
            
            # Look for bullet separator (• or ·) in the text
            # fbref uses middle dot (·) not bullet (•)
            separator = '·' if '·' in text else '•' if '•' in text else None
            
            if separator:
                # Split by separator and extract parts
                # Remove the player name from the beginning if present
                text_after_name = text
                if name in text:
                    # Find where the name ends
                    name_pos = text.find(name)
                    if name_pos >= 0:
                        text_after_name = text[name_pos + len(name):].strip()
                
                parts = [p.strip() for p in text_after_name.split(separator)]
                
                # Filter out empty parts
                parts = [p for p in parts if p]
                
                if len(parts) >= 1:
                    years_played = parts[0].strip()
                if len(parts) >= 2:
                    position = parts[1].strip()
                if len(parts) >= 3:
                    squad_history = parts[2].strip()
            
            # If we didn't find bullet pattern, try to extract from the text structure
            # Sometimes the format might be different
            if not years_played and not position:
                # Try to find patterns in the text
                # Years usually contain 4-digit years or year ranges
                year_match = re.search(r'(\d{4}[–-]\d{4}|\d{4})', text)
                if year_match:
                    years_played = year_match.group(1)
            
            # Parse years_played into YearStarted and YearEnded
            year_started = ''
            year_ended = ''
            
            if years_played:
                # Check if it's a range (e.g., "2017-2026") or single year (e.g., "1958")
                if '–' in years_played or '-' in years_played:
                    # It's a range
                    # Handle both en-dash (–) and hyphen (-)
                    year_parts = re.split(r'[–-]', years_played)
                    if len(year_parts) >= 1:
                        year_started = year_parts[0].strip()
                    if len(year_parts) >= 2:
                        year_ended = year_parts[1].strip()
                else:
                    # Single year
                    year_started = years_played.strip()
                    # If it's a single year and the player is active, year_ended might be current year
                    # But we'll leave it empty for now since we don't know if they're still playing
                    year_ended = ''
            
            footballers.append({
                'Name': name,
                'URL': player_url,
                'YearStarted': year_started,
                'YearEnded': year_ended,
                'Position': position,
                'SquadHistory': squad_history,
                'IsActive': 'Yes' if is_active else 'No'
            })
    
    print(f"\nExtracted {len(footballers)} players")
    return footballers

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python scrape_footballers.py <html_file>")
        print("Example: python scrape_footballers.py data/fbref.html")
        sys.exit(1)
    
    html_file = sys.argv[1]
    print(f"Reading from HTML file: {html_file}")
    footballers = scrape_from_html_file(html_file)
    
    if not footballers:
        print("No footballers found. Exiting.")
        sys.exit(1)
    
    # Save to CSV
    output_file = 'data/footballers_fbref.csv'
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['Name', 'URL', 'YearStarted', 'YearEnded', 'Position', 'SquadHistory', 'IsActive']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(footballers)
    
    print(f"\nSaved {len(footballers)} footballers to {output_file}")
    
    # Print statistics
    print("\nStatistics:")
    print(f"  Total footballers: {len(footballers)}")
    active_count = sum(1 for f in footballers if f.get('IsActive') == 'Yes')
    print(f"  Active players: {active_count}")
    with_position = sum(1 for f in footballers if f.get('Position'))
    print(f"  With position: {with_position}")
    with_years = sum(1 for f in footballers if f.get('YearStarted'))
    print(f"  With year started: {with_years}")

