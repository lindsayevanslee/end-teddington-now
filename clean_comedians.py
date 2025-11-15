#!/usr/bin/env python3
"""
Clean up the scraped comedians data:
1. Filter out deceased comedians
2. Deduplicate by name, prioritizing Stand-up comedians and Comedy panel game regulars
"""

import csv
from collections import defaultdict

def prioritize_type(type_name):
    """
    Return a priority score for type. Lower number = higher priority.
    Stand-up comedians and Comedy panel game regulars get highest priority.
    """
    priority_map = {
        'Stand-up comedians': 1,
        'Comedy panel game regulars': 2,
        'Sketch show/alternative comedians': 3,
        'Impressionists': 4,
        'Satirists': 5,
    }
    return priority_map.get(type_name, 100)  # Default low priority for others

def clean_comedians(input_file, output_file):
    """Clean the comedians data"""
    
    # Read the input CSV
    comedians_by_name = defaultdict(list)
    
    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filter out deceased comedians
            if row['DeathYear'] and row['DeathYear'].strip():
                continue
            
            name = row['Name'].strip()
            if not name:
                continue
            
            comedians_by_name[name].append(row)
    
    print(f"Found {len(comedians_by_name)} unique living comedians")
    
    # Deduplicate: for each name, pick the best entry
    cleaned_comedians = []
    
    for name, entries in comedians_by_name.items():
        if len(entries) == 1:
            # No duplicates, just add it
            cleaned_comedians.append(entries[0])
        else:
            # Multiple entries - pick the one with highest priority type
            # Sort by priority (lower number = higher priority)
            entries_sorted = sorted(entries, key=lambda x: prioritize_type(x['Type']))
            best_entry = entries_sorted[0].copy()
            
            # Merge data from other entries: keep birth year from any entry that has it
            for entry in entries:
                if entry['BirthYear'] and entry['BirthYear'].strip():
                    if not best_entry['BirthYear'] or not best_entry['BirthYear'].strip():
                        best_entry['BirthYear'] = entry['BirthYear']
                    break  # Use first available birth year
            
            # Keep URL from best entry (or first available)
            if not best_entry['URL'] or not best_entry['URL'].strip():
                for entry in entries:
                    if entry['URL'] and entry['URL'].strip():
                        best_entry['URL'] = entry['URL']
                        break
            
            cleaned_comedians.append(best_entry)
            
            # Log what we're doing for duplicates
            types = [e['Type'] for e in entries]
            if len(set(types)) > 1:
                print(f"  {name}: {len(entries)} entries, keeping '{best_entry['Type']}' (from: {', '.join(set(types))})")
    
    # Sort by name for easier reading
    cleaned_comedians.sort(key=lambda x: x['Name'])
    
    # Write to output CSV
    print(f"\nWriting {len(cleaned_comedians)} cleaned entries to {output_file}...")
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        if cleaned_comedians:
            fieldnames = ['Name', 'URL', 'Type', 'BirthYear', 'DeathYear']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(cleaned_comedians)
    
    print(f"Done! Saved {len(cleaned_comedians)} comedians to {output_file}")
    
    # Print statistics
    type_counts = defaultdict(int)
    for comedian in cleaned_comedians:
        type_counts[comedian['Type']] += 1
    
    print(f"\nStatistics:")
    print(f"  Total comedians: {len(cleaned_comedians)}")
    print(f"  With birth year: {sum(1 for c in cleaned_comedians if c['BirthYear'] and c['BirthYear'].strip())}")
    print(f"  With Wikipedia URL: {sum(1 for c in cleaned_comedians if c['URL'] and c['URL'].strip())}")
    print(f"\nBy type:")
    for type_name, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {type_name}: {count}")

def main():
    """Main function"""
    input_file = 'data/comedians_wikipedia.csv'
    output_file = 'data/comedians_cleaned.csv'
    
    clean_comedians(input_file, output_file)

if __name__ == '__main__':
    main()

