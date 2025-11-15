#!/usr/bin/env python3
"""
Scrape British comedians from Wikipedia and create a CSV file.
"""

import requests
from bs4 import BeautifulSoup
import re
import csv
from urllib.parse import urljoin, urlparse

def extract_years(text):
    """Extract birth and death years from text like 'born 1970' or '1943–1995'"""
    birth_year = None
    death_year = None
    
    # Pattern for "born YYYY"
    born_match = re.search(r'born\s+(\d{4})', text, re.IGNORECASE)
    if born_match:
        birth_year = int(born_match.group(1))
    
    # Pattern for "YYYY–YYYY" (birth-death)
    year_range = re.search(r'(\d{4})\s*[–-]\s*(\d{4})', text)
    if year_range:
        birth_year = int(year_range.group(1))
        death_year = int(year_range.group(2))
    
    # Pattern for "(YYYY–YYYY)" in parentheses
    paren_range = re.search(r'\((\d{4})\s*[–-]\s*(\d{4})\)', text)
    if paren_range:
        birth_year = int(paren_range.group(1))
        death_year = int(paren_range.group(2))
    
    return birth_year, death_year

def extract_name_and_info(text):
    """Extract name and additional info from list item text"""
    # Remove Wikipedia citation markers like [1], [edit], etc.
    text = re.sub(r'\[.*?\]', '', text)
    text = text.strip()
    
    # Split on comma or parentheses to separate name from info
    # Name is typically before the first comma or opening parenthesis
    name_match = re.match(r'^([^,(]+)', text)
    if name_match:
        name = name_match.group(1).strip()
        # Clean up name - remove extra whitespace
        name = ' '.join(name.split())
        return name, text
    return None, text

def scrape_wikipedia_page():
    """Scrape the British comedians Wikipedia page"""
    url = "https://en.wikipedia.org/wiki/List_of_British_comedians"
    
    # Wikipedia requires a User-Agent header to identify the bot
    # Using a descriptive User-Agent is preferred by Wikipedia
    # Format: ProjectName/Version (URL; contact email)
    headers = {
        'User-Agent': 'EndTeddingtonNowBot/1.0 (https://endteddingtonnow.com; web scraping for comedy purposes)'
    }
    
    print(f"Fetching {url}...")
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    comedians = []
    base_url = "https://en.wikipedia.org"
    processed_lists = set()  # Track which lists we've already processed
    
    # Find the main content area
    content = soup.find('div', {'id': 'mw-content-text'})
    if not content:
        print("Warning: Could not find main content area")
        return comedians
    
    # Find all h2 and h3 headings within the content
    headings = content.find_all(['h2', 'h3'])
    
    current_type = None
    
    for heading in headings:
        # Get section type from heading
        heading_text = heading.get_text().strip()
        # Remove [edit] markers and other annotations
        heading_text = re.sub(r'\[.*?\]', '', heading_text).strip()
        
        # Skip certain headings
        if heading_text in ['Contents', 'See also', 'References', 'Navigation menu', '']:
            continue
        
        # Check if this is a main section (h2) or subsection (h3)
        is_single_letter_subheader = False
        if heading.name == 'h2':
            current_type = heading_text
        elif heading.name == 'h3':
            # Check if this is a single-letter alphabetical subheader (A, B, C, etc.)
            # These are just organizational and shouldn't be part of the type
            if len(heading_text.strip()) == 1 and heading_text.strip().isalpha():
                # Don't update current_type, keep the parent section type
                # But we still need to process the lists that follow
                is_single_letter_subheader = True
            # For other subsections, combine with parent if available
            elif current_type:
                current_type = f"{current_type} - {heading_text}"
            else:
                current_type = heading_text
        
        # Find the next heading to know where this section ends
        # For single-letter subheaders, we want to find the next h2 or h3 that's not another single letter
        if is_single_letter_subheader:
            # Find next heading that's not a single letter
            next_heading = heading.find_next(['h2', 'h3'])
            while next_heading:
                next_text = re.sub(r'\[.*?\]', '', next_heading.get_text().strip())
                if next_heading.name == 'h2' or (next_heading.name == 'h3' and 
                    not (len(next_text) == 1 and next_text.isalpha())):
                    break
                next_heading = next_heading.find_next(['h2', 'h3'])
        else:
            next_heading = heading.find_next(['h2', 'h3'])
        
        # Only process lists if we have a valid current_type
        if not current_type:
            continue
        
        # Find all ul/ol elements between this heading and the next
        current_list = heading.find_next(['ul', 'ol'])
        while current_list:
            # Skip if we've already processed this list
            list_id = id(current_list)
            if list_id in processed_lists:
                current_list = current_list.find_next(['ul', 'ol'])
                continue
            
            # For single-letter subheaders, we want to process lists until the next non-single-letter heading
            # For regular headings, stop at the next heading
            should_stop = False
            if next_heading:
                # Check if current_list is after next_heading
                prev_heading = current_list.find_previous(['h2', 'h3'])
                if prev_heading and prev_heading != heading:
                    prev_text = re.sub(r'\[.*?\]', '', prev_heading.get_text().strip())
                    # If the previous heading is the next_heading (and it's not a single letter we're processing), stop
                    if prev_heading == next_heading:
                        should_stop = True
                    # If it's a single-letter subheader that's not our current heading, it's part of the same section
                    elif not (prev_heading.name == 'h3' and len(prev_text) == 1 and prev_text.isalpha() and 
                             is_single_letter_subheader):
                        # This list belongs to a different section
                        should_stop = True
            
            if should_stop:
                break
            
            # Mark this list as processed
            processed_lists.add(list_id)
            
            # Process all list items
            for li in current_list.find_all('li', recursive=False):
                # Check if this list item has a nested list (group with sub-items)
                nested_list = li.find(['ul', 'ol'], recursive=False)
                
                if nested_list:
                    # This is a group - process the nested items instead
                    for sub_li in nested_list.find_all('li', recursive=False):
                        text = sub_li.get_text()
                        
                        # Skip empty items
                        if not text.strip():
                            continue
                        
                        name, full_text = extract_name_and_info(text)
                        if not name:
                            continue
                        
                        # Extract years
                        birth_year, death_year = extract_years(full_text)
                        
                        # Try to find the Wikipedia link
                        wiki_url = None
                        link = sub_li.find('a', href=True)
                        if link and link.get('href'):
                            href = link.get('href')
                            # Only include links to Wikipedia articles (not external links, categories, etc.)
                            if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
                                wiki_url = urljoin(base_url, href)
                        
                        comedians.append({
                            'Name': name,
                            'URL': wiki_url or '',
                            'Type': current_type or 'Unknown',
                            'BirthYear': birth_year if birth_year else '',
                            'DeathYear': death_year if death_year else ''
                        })
                else:
                    # Regular list item (not a group)
                    text = li.get_text()
                    
                    # Skip empty items
                    if not text.strip():
                        continue
                    
                    name, full_text = extract_name_and_info(text)
                    if not name:
                        continue
                    
                    # Extract years
                    birth_year, death_year = extract_years(full_text)
                    
                    # Try to find the Wikipedia link
                    wiki_url = None
                    link = li.find('a', href=True)
                    if link and link.get('href'):
                        href = link.get('href')
                        # Only include links to Wikipedia articles (not external links, categories, etc.)
                        if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
                            wiki_url = urljoin(base_url, href)
                    
                    comedians.append({
                        'Name': name,
                        'URL': wiki_url or '',
                        'Type': current_type or 'Unknown',
                        'BirthYear': birth_year if birth_year else '',
                        'DeathYear': death_year if death_year else ''
                    })
            
            # Find the next list
            current_list = current_list.find_next(['ul', 'ol'])
            # Check if we've gone past the next heading
            if next_heading and current_list:
                # Simple check: if the list comes after the next heading, stop
                try:
                    if (hasattr(current_list, 'sourceline') and hasattr(next_heading, 'sourceline') and
                        current_list.sourceline > next_heading.sourceline):
                        break
                except:
                    # If we can't compare, use a different approach
                    # Check if next_heading is between heading and current_list
                    between = heading.find_next_siblings()
                    found_next = False
                    found_list = False
                    for elem in between:
                        if elem == next_heading:
                            found_next = True
                        if elem == current_list:
                            found_list = True
                        if found_next and not found_list:
                            # We passed the next heading before finding the list
                            current_list = None
                            break
    
    return comedians

def main():
    """Main function to scrape and save data"""
    print("Starting scrape...")
    comedians = scrape_wikipedia_page()
    
    print(f"Found {len(comedians)} comedians")
    
    # Save to CSV
    output_file = 'data/comedians_wikipedia.csv'
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        if comedians:
            writer = csv.DictWriter(f, fieldnames=['Name', 'URL', 'Type', 'BirthYear', 'DeathYear'])
            writer.writeheader()
            writer.writerows(comedians)
    
    print(f"Saved to {output_file}")
    
    # Print some statistics
    with_birth = sum(1 for c in comedians if c['BirthYear'])
    with_death = sum(1 for c in comedians if c['DeathYear'])
    with_url = sum(1 for c in comedians if c['URL'])
    
    print(f"\nStatistics:")
    print(f"  Total comedians: {len(comedians)}")
    print(f"  With birth year: {with_birth}")
    print(f"  With death year: {with_death}")
    print(f"  With Wikipedia URL: {with_url}")
    
    # Show first few entries
    print(f"\nFirst 5 entries:")
    for i, comedian in enumerate(comedians[:5], 1):
        print(f"  {i}. {comedian['Name']} ({comedian['Type']})")

if __name__ == '__main__':
    main()

