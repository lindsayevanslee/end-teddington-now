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

def extract_double_act_members(url, headers, double_act_name=None):
    """Extract individual comedian names from a double act Wikipedia page"""
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        members = []
        
        # Extract potential surnames from double act name (e.g., "Baddiel and Skinner" -> ["Baddiel", "Skinner"])
        target_surnames = []
        if double_act_name:
            # Remove common words and split
            name_parts = re.sub(r'\b(and|&|the)\b', ' ', double_act_name, flags=re.IGNORECASE)
            name_parts = [part.strip() for part in name_parts.split() if part.strip()]
            # Take the last 2-3 words as potential surnames (double acts usually have 2 members)
            if len(name_parts) >= 2:
                target_surnames = name_parts[-2:]  # Last 2 words
            elif len(name_parts) == 1:
                # Single word - might be a compound name, try to split
                target_surnames = [name_parts[0]]
        
        # Method 1: Look for infobox with Members/Stars/Cast row
        infobox = soup.find('table', class_='infobox')
        if infobox:
            for row in infobox.find_all('tr'):
                th = row.find('th')
                if th and ('member' in th.get_text().lower() or 'star' in th.get_text().lower() or 'cast' in th.get_text().lower()):
                    td = row.find('td')
                    if td:
                        # Find all links to Wikipedia articles
                        links = td.find_all('a', href=True)
                        for link in links:
                            href = link.get('href', '')
                            if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
                                member_name = link.get_text().strip()
                                if member_name:
                                    member_url = urljoin('https://en.wikipedia.org', href)
                                    members.append({
                                        'name': member_name,
                                        'url': member_url
                                    })
        
        # Method 2: Use surname matching - search for names containing surnames from double act name
        if not members and target_surnames:
            content = soup.find('div', {'id': 'mw-content-text'})
            if content:
                # Get first few paragraphs (sometimes members are mentioned in second paragraph)
                paragraphs = content.find_all('p', limit=3)
                page_title = soup.find('h1', class_='firstHeading')
                page_title_text = page_title.get_text().strip() if page_title else ""
                
                for first_p in paragraphs:
                    if not first_p:
                        continue
                    # Look for links that contain the target surnames
                    links = first_p.find_all('a', href=True)
                    for link in links:
                        href = link.get('href', '')
                        if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
                            link_text = link.get_text().strip()
                            # Skip if it's the same as the page title
                            if link_text.lower() not in page_title_text.lower() and len(link_text) > 3:
                                # Check if this name contains any of the target surnames
                                link_lower = link_text.lower()
                                matches_surname = any(surname.lower() in link_lower for surname in target_surnames)
                                
                                if matches_surname:
                                    # Additional validation: must look like a person's name
                                    words = link_text.split()
                                    # Exclude place names and organizations
                                    exclude_place_words = ['united', 'kingdom', 'states', 'england', 'scotland', 'wales', 'ireland', 'city', 'county']
                                    
                                    if (2 <= len(words) <= 4 and 
                                        all(word[0].isupper() if word else False for word in words) and
                                        len(link_text) < 50 and
                                        not link_text.isupper() and
                                        not any(word.lower() in exclude_place_words for word in words)):
                                        member_url = urljoin('https://en.wikipedia.org', href)
                                        # Avoid duplicates (by exact name match)
                                        if not any(m['name'] == link_text for m in members):
                                            members.append({
                                                'name': link_text,
                                                'url': member_url
                                            })
                    # If we found members matching all surnames, we're probably done
                    if len(members) >= len(target_surnames):
                        break
        
        # Method 3: Look in the first paragraph for links to individual comedians (fallback)
        if not members:
            content = soup.find('div', {'id': 'mw-content-text'})
            if content:
                # Get first few paragraphs (sometimes members are mentioned in second paragraph)
                paragraphs = content.find_all('p', limit=3)
                page_title = soup.find('h1', class_='firstHeading')
                page_title_text = page_title.get_text().strip() if page_title else ""
                
                for first_p in paragraphs:
                    if not first_p:
                        continue
                    # Look for links that might be to individual comedians
                    # Usually double act pages mention the members in the first sentence
                    links = first_p.find_all('a', href=True)
                    for link in links:
                        href = link.get('href', '')
                        if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
                            link_text = link.get_text().strip()
                            # Skip if it's the same as the page title or common words
                            if link_text.lower() not in page_title_text.lower() and len(link_text) > 3:
                                # Check if this looks like a person's name
                                words = link_text.split()
                                common_words = ['the', 'and', 'or', 'with', 'from', 'their', 'they', 'comedy', 'show', 'series', 
                                              'talk', 'festival', 'fringe', 'theatre', 'theater', 'end', 'west', 'east', 'north', 'south',
                                              'humour', 'humor', 'black', 'surreal', 'mighty', 'boosh', 'bbc', 'club', 'only', 'but', 'also',
                                              'greater', 'manchester', 'london', 'live', 'three']
                                
                                # Exclude patterns that indicate organizations, places, or shows
                                exclude_patterns = ['bbc', 'club', 'only', 'but also', 'greater', 'manchester', 'london live']
                                exclude_place_words = ['united', 'kingdom', 'states', 'england', 'scotland', 'wales', 'ireland', 'city', 'county']
                                
                                # Filter: must be 2-4 words, each word capitalized, not in common words or exclude patterns
                                if (2 <= len(words) <= 4 and 
                                    all(word[0].isupper() if word else False for word in words) and
                                    link_text.lower() not in common_words and
                                    not any(word.lower() in common_words for word in words) and
                                    not any(pattern in link_text.lower() for pattern in exclude_patterns) and
                                    not any(word.lower() in exclude_place_words for word in words) and
                                    len(link_text) < 50 and
                                    # Must look like a person's name (typically first name + last name pattern)
                                    not link_text.isupper()):  # Exclude all-caps (often acronyms)
                                    member_url = urljoin('https://en.wikipedia.org', href)
                                    # Avoid duplicates
                                    if not any(m['name'] == link_text for m in members):
                                        members.append({
                                            'name': link_text,
                                            'url': member_url
                                        })
                    # If we found at least 2 members, we're probably done
                    if len(members) >= 2:
                        break
        
        # Method 4: Look for a "Members" or "Cast" section
        if not members:
            content = soup.find('div', {'id': 'mw-content-text'})
            if content:
                for heading in content.find_all(['h2', 'h3']):
                    text = heading.get_text().lower()
                    if 'member' in text or 'cast' in text:
                        # Get next list or paragraph
                        next_elem = heading.find_next(['ul', 'ol', 'p'])
                        if next_elem:
                            links = next_elem.find_all('a', href=True)
                            for link in links:
                                href = link.get('href', '')
                                if href.startswith('/wiki/') and ':' not in href.split('/wiki/')[1]:
                                    member_name = link.get_text().strip()
                                    # Additional validation: must look like a person's name
                                    words = member_name.split()
                                    exclude_place_words = ['united', 'kingdom', 'states', 'england', 'scotland', 'wales', 'ireland', 'city', 'county']
                                    
                                    if (member_name and len(member_name) > 3 and
                                        2 <= len(words) <= 4 and
                                        all(word[0].isupper() if word else False for word in words) and
                                        not any(word.lower() in exclude_place_words for word in words) and
                                        not member_name.isupper()):
                                        member_url = urljoin('https://en.wikipedia.org', href)
                                        if not any(m['name'] == member_name for m in members):
                                            members.append({
                                                'name': member_name,
                                                'url': member_url
                                            })
                            if members:
                                break
        
        return members
    except Exception as e:
        print(f"    Warning: Could not extract members from {url}: {e}")
        return []

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
    
    # Store headers for use in extract_double_act_members
    scrape_wikipedia_page.headers = headers
    
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
                    
                    # Special handling for Comedy double acts: extract individual members
                    if current_type == 'Comedy double acts' and wiki_url:
                        print(f"  Extracting members from double act: {name}")
                        members = extract_double_act_members(wiki_url, scrape_wikipedia_page.headers, double_act_name=name)
                        if members:
                            # Add each member as an individual comedian
                            for member in members:
                                comedians.append({
                                    'Name': member['name'],
                                    'URL': member['url'],
                                    'Type': current_type or 'Unknown',
                                    'BirthYear': '',  # Will need to be filled from member's page if needed
                                    'DeathYear': ''
                                })
                            continue  # Skip adding the group name
                        else:
                            print(f"    Could not extract members, keeping group name: {name}")
                    
                    # Add the regular entry (or group name if member extraction failed)
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

