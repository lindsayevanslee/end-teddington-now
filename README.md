# End Teddington Now!

This [website](https://endteddingtonnow.com) displays the results of a probability model that calculates the likelihood of various comedian-footballer pairings being seen in Teddington by Max Rushden during the era known as the "Teddington Days," as described in the podcast [What Did You Do Yesterday?](https://podcasts.apple.com/us/podcast/what-did-you-do-yesterday-with-max-rushden-david-odoherty/id1765600990).


## Data Preparation

Both the comedians and footballers data goes through these steps in order to prep it for the statistical model: 

1. Scrape data from public sources
2. Clean the data
3. Enrich the data with additional information


### Scrape data from public sources

The project starts with raw data scraped from public sources:

- **Comedians**: Scraped from Wikipedia's "List of British Comedians" page 
  - This page is scraped using the `scrape_comedians.py` script.
  - Includes: Name, Wikipedia URL, Type (stand-up, panel show regular, etc.), Birth Year, Death Year
  - Stored in: `data/comedians_wikipedia.csv`

- **Footballers**: Scraped from fbref.com's England players page
  - This page is scraped using the `scrape_footballers.py` script.
  - Includes: Name, Player URL, Years Played, Position, Squad History, Active Status
  - Stored in: `data/footballers_fbref.csv`


### Clean the data

The data goes through several processing steps:

1. **`clean_comedians.py`** - Removes deceased comedians, deduplicates entries, and prioritizes certain comedian types. Creates file: `data/comedians_cleaned.csv`

2. **`clean_footballers.py`** - Filters footballers to only include those who have played for England's senior men's team (verified against englandfootball.com). Creates file: `data/footballers_cleaned.csv`


### Enrich the data with additional information

1. **`enrich_comedians.py`** - Adds additional data for each comedian:
   - Wikipedia page length (as a proxy for fame)
   - Current age (calculated from birth year)
   - Birthplace and distance from Teddington (using geocoding)
   - Creates file: `data/comedians_enriched.csv`

2. **`enrich_footballers.py`** - Adds additional data for each footballer:
   - Birthplace and distance from Teddington
   - Current age
   - Creates file: `data/footballers_enriched.csv`



## Statistical Model

The probability calculations are performed by `calculate_probabilities.py`, which uses a weighted scoring system. The model considers multiple factors that influence how likely is to have been seen by Max in Teddington. The model here is just a simple best guess based on the limited information available and will be updated as more data becomes available.

### Comedian Probability Model

For each comedian, the model calculates a score based on four factors:

1. **Birthplace's distance from Teddington (50% weight)** - The most important factor
   - Within 3 km (walking distance): Score of 1.0
   - Within 10 km (very local): Score of 0.8
   - Within 20 km (Greater London): Score of 0.4
   - Within 50 km (commutable): Score of 0.2
   - Further away: Score of 0.05
   - Unknown location: Score of 0.1

2. **Age/Mobility (20% weight)** - Considers how mobile someone is likely to be
   - Ages 30-60 (peak mobility): Score of 1.0
   - Ages 25-70: Score of 0.7
   - Younger than 25 or older than 70: Score of 0.4
   - Unknown age: Score of 0.5

3. **Fame Level (20% weight)** - Uses Wikipedia page length as a proxy for fame
   - Very famous (page > 10,000 characters): Score of 0.1 (less likely to be out and about and hanging their own posters)
   - Well known (page > 5,000 characters): Score of 0.3
   - Known (page > 2,000 characters): Score of 0.9
   - Less known: Score of 0.3

4. **Local Connection (10% weight)** - Bonus for being from the local area
   - Born in Richmond, Twickenham, Teddington, Kingston, or Hampton: Score of 1.0
   - Born in London: Score of 0.3
   - No local connection: Score of 0.0

These four scores are combined using their weights (50% + 20% + 20% + 10% = 100%) to create a raw probability score. All comedians who have died are automatically given a probability of 0.

### Footballer Probability Model

For each footballer, the model uses a similar approach but with different factors:

1. **Active Status (base multiplier)** - Adjusts the entire score based on career status
   - Recently retired (within 10 years): Highest score (multiplier of 1.0) - most likely to be seen
   - Long retired (more than 10 years): Moderate score (multiplier of 0.6) - less likely than recently retired, but more likely than active players
   - Currently active players: Lowest score (multiplier of 0.3) - least likely to be seen

2. **Birthplace's distance from Teddington (40% weight)** - Similar to comedians but with slightly different thresholds
   - Within 5 km: Score of 1.0
   - Within 15 km: Score of 0.7
   - Within 30 km: Score of 0.4
   - Within 60 km: Score of 0.2
   - Further away: Score of 0.02

3. **Club Connection (30% weight)** - Considers which football clubs they've played for
   - Southwest London clubs (Chelsea, Fulham, Brentford, QPR, Wimbledon): Score of 1.0
   - Other London clubs: Score of 0.5
   - Non-London clubs: Score of 0.1

4. **Age Factor (20% weight)** - Similar to comedians but adjusted for football careers
   - Ages 25-40 (peak playing age): Score of 1.0
   - Ages 40-55 (recently retired, still mobile): Score of 0.7
   - Under 25: Score of 0.6
   - Over 55: Score of 0.3

5. **Career Prominence (10% weight)** - Based on career length
   - 15+ years: Score of 0.9
   - 10-14 years: Score of 0.7
   - 5-9 years: Score of 0.5
   - Less than 5 years: Score of 0.3

The active status multiplier is applied to the weighted combination of the other four factors.

### Clues for Valid Combinations

Key pieces of information shared on the podcast are used to determine valid combinations:

- Max confirmed that both the comedian and the footballer were men, so women are given an automatic probability of 0.
- Max stated on the podcast dated 2025-11-25 that the correct answer was showing a probability of 0.0001% on this site. A snapshot of the data he was looking at was archived in `data/snapshots/wdydy_2025-11-25` and is used to determine the valid combinations.

### Normalization

After calculating raw probability scores for all individuals, the model normalizes them so that all probabilities within each group (comedians and footballers) sum to 1.0 (or 100%). This means:

- Each comedian's probability represents their share of the total "comedian probability pool"
- Each footballer's probability represents their share of the total "footballer probability pool"
- When you multiply a comedian's probability by a footballer's probability, you get the combined probability of that specific pairing

### Output Data

The final processed data files used by the website:

- **`data/comedians_probability.csv`** - Contains comedian names, URLs (for unique identification), and their calculated probability scores
- **`data/footballers_probability.csv`** - Contains footballer names, URLs (for unique identification), and their calculated probability scores
- **`data/combinations_2025-11-25.csv`** - Contains all valid comedian-footballer pairings that have a combined probability matching a specific threshold (0.000001). This file is used to filter and renormalize conditional probabilities in the interactive website.

These files are used directly by the Quarto website to populate the interactive tables and determine valid pairings.


## The Website

The website is built using Quarto. The main file is `index.qmd`, which contains:

- A dynamic counter showing days since the collective nightmare of the Teddington Quiz began
- An interactive Shiny app (using Shinylive) that displays:
  - Two searchable tables (comedians and footballers) with their individual probabilities
  - The ability to select one comedian and one footballer
  - A calculation showing the combined probability of that pairing

The website uses the processed probability CSV files (`comedians_probability.csv` and `footballers_probability.csv`) to populate the tables. When a user selects a pairing, the website multiplies the two probabilities together to show the combined likelihood.

### Interactive Features

The website includes several interactive features:

1. **Search Functionality**: Both tables have search boxes that filter results in real-time as you type.

2. **Selection Behavior**: 
   - When you select a comedian or footballer, all other options in that list disappear, showing only the selected item
   - A "CLEAR SELECTION" button allows you to reset your choices and see all options again

3. **Conditional Probability Renormalization**:
   - When you select one item (e.g., a footballer), the other list (comedians) automatically filters to show only valid pairings from the combinations file `data/combinations_2025-11-25.csv`
   - The probabilities in the filtered list are renormalized to sum to 100%, representing conditional probabilities (e.g. the probability of the comedian being correct given the selected footballer is correct)
   - The first-selected item always displays its original probability, while the second list shows renormalized conditional probabilities
   - The final calculation uses: `original_probability_of_first_selected × renormalized_probability_of_second_selected`

4. **Unique Row Identification**: 
   - The system uses DataFrame indices to uniquely identify each row, ensuring that even if multiple people share the same name (e.g., multiple "Wayne Brown" entries), only the specific row you click is selected and used in calculations

5. **Valid Combinations**: 
   - The website uses `data/combinations_2025-11-25.csv` to determine which comedian-footballer pairings are valid (this is combinations of comedian/footballer showing a probability of 0.0001% in the snapshot of the data Max was looking at on the podcast dated 2025-11-25)
   - Only pairings that exist in this file are considered when filtering and renormalizing probabilities
   - This ensures that the conditional probabilities reflect only realistic pairings based on the underlying data

## Running the Project

### Prerequisites

- Python 3.x
- R (for Quarto)
- Quarto

### Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the data pipeline (in order):
   ```bash
   python scrape_comedians.py
   python clean_comedians.py
   python enrich_comedians.py
   python scrape_footballers.py
   python clean_footballers.py
   python enrich_footballers.py
   python calculate_probabilities.py
   ```

3. Build the website:
   ```bash
   quarto render
   ```

The website will be generated in the `_site/` directory.

## Notes

The data and probabilities will change as the underlying data sources are updated and the model is refined. Suggestions for improvement and pull requests are welcome. Let's end this.

