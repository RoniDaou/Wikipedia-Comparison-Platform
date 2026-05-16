"""
Wikipedia Infobox Scraper
Collects semi-structured data from Wikipedia country infoboxes
"""

import requests
from bs4 import BeautifulSoup, NavigableString
import re
from typing import Dict, List, Optional
from datetime import datetime
import time
import unicodedata


class WikipediaInfoboxScraper:
    """Scrapes Wikipedia infoboxes for country information"""

    def __init__(self, database=None):
        self.base_url = "https://en.wikipedia.org/wiki/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Educational Project) WikipediaInfoboxScraper/1.0'
        })
        self.database = database

        self.country_disambiguations = {
            'georgia': 'Georgia_(country)',
            'congo': 'Republic_of_the_Congo',
            'democratic republic of the congo': 'Democratic_Republic_of_the_Congo',
            'republic of the congo': 'Republic_of_the_Congo',
            'congo-brazzaville': 'Republic_of_the_Congo',
            'congo-kinshasa': 'Democratic_Republic_of_the_Congo',
            'guinea': 'Guinea',
            'korea': 'Korea',
            'north korea': 'North_Korea',
            'south korea': 'South_Korea',
            'macedonia': 'North_Macedonia',
            'north macedonia': 'North_Macedonia',
            'ireland': 'Republic_of_Ireland',
            'china': 'China',
            'dominica': 'Dominica',
        }

    # ── Name helpers ──────────────────────────────────────────────────────────

    def _normalize_country_name(self, country_name: str) -> str:
        lower_name = country_name.strip().lower()
        if lower_name in self.country_disambiguations:
            return self.country_disambiguations[lower_name]
        return country_name.strip().title()

    def _normalize_unicode(self, text: str) -> str:
        normalized = unicodedata.normalize('NFKD', text)
        return normalized.encode('ASCII', 'ignore').decode('ASCII')

    def _normalize_case(self, text: str) -> str:
        lowercase_words = {'of', 'the', 'and', 'a', 'an', 'for', 'to', 'in', 'on', 'at'}
        words = text.split()
        result = []
        for i, word in enumerate(words):
            if i == 0:
                result.append(word.capitalize())
            elif word.lower() in lowercase_words:
                result.append(word.lower())
            else:
                result.append(word.capitalize())
        return ' '.join(result)

    def _format_country_name_for_display(self, country_name: str) -> str:
        name = re.sub(r'\s*\([^)]*\)', '', country_name)
        name = name.replace('_', ' ')
        name = self._normalize_unicode(name)
        name = ' '.join(name.split())
        return self._normalize_case(name).strip()

    # ── DB helpers ────────────────────────────────────────────────────────────

    def country_exists_in_db(self, country_name: str) -> bool:
        if not self.database:
            return False
        normalized_name = self._normalize_country_name(country_name)
        display_name = self._format_country_name_for_display(normalized_name)
        return self.database.get_country(display_name) is not None

    # ── Main scrape ───────────────────────────────────────────────────────────

    def get_country_infobox(self, country_name: str,
                            force_rescrape: bool = False) -> Optional[Dict]:
        if not force_rescrape and self.country_exists_in_db(country_name):
            normalized_name = self._normalize_country_name(country_name)
            display_name = self._format_country_name_for_display(normalized_name)
            print(f"⏭️  Skipping {display_name} - already in database")
            return None

        try:
            normalized_name = self._normalize_country_name(country_name)
            url = self.base_url + normalized_name.replace(' ', '_')
            print(f"Fetching: {url}")

            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            infobox = soup.find('table', {'class': 'infobox'})

            if not infobox:
                print(f"No infobox found for {normalized_name}")
                return None

            display_name = self._format_country_name_for_display(normalized_name)
            infobox_data = self._parse_infobox(infobox, display_name, url)
            print(f"✅ Successfully scraped: {display_name}")
            return infobox_data

        except requests.Timeout:
            print(f"Timeout error fetching {country_name}")
            return None
        except requests.RequestException as e:
            print(f"Error fetching {country_name}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error for {country_name}: {e}")
            return None

    # ── Infobox parser ────────────────────────────────────────────────────────

    def _parse_infobox(self, infobox, country_name: str, url: str) -> Dict:
        data = {
            'country_name': country_name,
            'source_url': url,
            'scraped_at': datetime.utcnow().isoformat(),
            'fields': {}
        }

        rows = infobox.find_all('tr')

        for row in rows:
            header     = row.find('th', {'scope': 'row'})
            value_cell = row.find('td')

            if header and value_cell:
                # FIX 1: separator=' ' prevents "Capitaland largest city"
                # FIX 2: strip trailing colon/space from field names
                #         e.g. 'German :' → 'German'
                field_name  = self._clean_text(header.get_text(separator=' '))
                field_name  = re.sub(r'\s*:\s*$', '', field_name).strip()
                # Strip leading bullet • and whitespace from field names
                field_name  = re.sub(r'^[•\s]+', '', field_name).strip()
                field_value = self._extract_value(value_cell)

                if not field_name or not field_value:
                    continue

                if field_name not in data['fields']:
                    data['fields'][field_name] = field_value
                else:
                    # FIX 3: skip exact duplicates entirely
                    if data['fields'][field_name] == field_value:
                        continue
                    # Different value — store with counter
                    counter = 2
                    new_key = f"{field_name} ({counter})"
                    while new_key in data['fields']:
                        counter += 1
                        new_key = f"{field_name} ({counter})"
                    data['fields'][new_key] = field_value

        return data

    # ── Value extractor ───────────────────────────────────────────────────────

    def _extract_value(self, cell) -> str:
        """
        Extract cell text while preserving hierarchy.

        Fixes applied:
          FIX 1 — Merged spans ("31.8medium inequality"):
                   Use get_text(separator=' ') everywhere and insert
                   NavigableString spaces between adjacent inline tags.
          FIX 2 — Duplicate pre-list summaries (Religion, Ethnic groups):
                   Only prepend the pre-list text if it does NOT look like
                   a duplicate summary of the list (heuristic: no '%' sign
                   and no heavy overlap with the first list item).
          FIX 3 — Punctuation-only lines left after Arabic stripping:
                   Filter out lines that contain no alphanumeric character.
        """
        # Remove style / script noise
        for tag in cell.find_all(['style', 'script']):
            tag.decompose()

        # FIX 1 — insert spaces between adjacent inline elements
        block_tags = {'div', 'p', 'li', 'ul', 'ol', 'tr', 'td', 'th',
                      'table', 'tbody', 'thead', 'br', 'hr'}
        for tag in cell.find_all(True):
            if tag.name not in block_tags:
                if not (tag.next_sibling and isinstance(tag.next_sibling, str)):
                    tag.insert_after(NavigableString(' '))

        # Collect pre-list text (text before the first <ul>/<ol>)
        pre_list_text = ""
        for child in cell.children:
            if hasattr(child, 'name') and child.name in ('ul', 'ol'):
                break
            if hasattr(child, 'get_text'):
                t = self._clean_text(child.get_text(separator=' '))
                if t:
                    pre_list_text = (pre_list_text + ' ' + t).strip()
            elif isinstance(child, str):
                t = self._clean_text(str(child))
                if t:
                    pre_list_text = (pre_list_text + ' ' + t).strip()

        all_lists = cell.find_all(['ul', 'ol'])

        # No list — return simple cleaned text
        if not all_lists:
            return self._clean_text(cell.get_text(separator=' '))

        # Find top-level list
        main_list = None
        for lst in all_lists:
            if lst.find_parent(['ul', 'ol']) is None:
                main_list = lst
                break
        if not main_list:
            main_list = all_lists[0]

        # IMPORTANT: define main_items BEFORE the pre_list duplicate check
        main_items = main_list.find_all('li', recursive=False)

        result_lines = []

        # FIX 2 — only prepend pre_list_text if it is not a duplicate summary
        if pre_list_text:
            # Get text of the first list item for overlap check
            first_item_text = ""
            if main_items:
                for content in main_items[0].children:
                    if isinstance(content, str):
                        first_item_text += content
                    elif content.name not in ['ul', 'ol']:
                        first_item_text += content.get_text(separator=' ')
                    else:
                        break
                first_item_text = self._clean_text(first_item_text).lower()

            is_duplicate = (
                '%' in pre_list_text or
                (first_item_text and first_item_text[:20] in pre_list_text.lower())
            )
            if not is_duplicate:
                result_lines.append(pre_list_text)

        # Process list items
        for li in main_items:
            main_text = ""
            for content in li.children:
                if isinstance(content, str):
                    main_text += content
                elif content.name not in ['ul', 'ol']:
                    main_text += content.get_text(separator=' ')
                else:
                    break
            main_text = self._clean_text(main_text)
            if main_text:
                result_lines.append(main_text)

            # Nested items
            for nested_list in li.find_all(['ul', 'ol'], recursive=False):
                nested_items = nested_list.find_all('li', recursive=False)
                for j, nested_li in enumerate(nested_items):
                    nested_text = self._clean_text(
                        nested_li.get_text(separator=' ')
                    )
                    prefix = "└── " if j == len(nested_items) - 1 else "├── "
                    result_lines.append(f"{prefix}{nested_text}")

        # FIX 3 — remove lines that are empty or punctuation-only
        cleaned_lines = [
            line for line in result_lines
            if re.search(r'[A-Za-z0-9]', line.lstrip('├└─ '))
        ]

        return '\n'.join(cleaned_lines) if cleaned_lines else self._clean_text(
            cell.get_text(separator=' ')
        )

    # ── Text cleaner ──────────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        """
        Clean text:
          - Remove citation markers [1], [ 1 ], [a], [ b ] etc.
          - Strip non-ASCII (Arabic, CJK, etc.)
          - Remove spaces inside parentheses: ( PPP ) → (PPP)
          - Remove spaces before superscripts: km 2 → km2
          - Collapse whitespace
        """
        # Remove citations: [1], [ 1 ], [a], [ b ], [10] etc.
        text = re.sub(r'\[\s*[\da-zA-Z]+\s*\]', '', text)

        # Strip BOM and zero-width characters
        text = re.sub(r'[\ufeff\u200b\u200c\u200d\u00ad]+', '', text)

        # Strip leading bullet points from field values and names
        text = re.sub(r'^[•\s]+', '', text)

        # Strip only Arabic, Hebrew, CJK scripts. Keep accented Latin (é, ö, etc.)
        text = re.sub(
            r'[؀-ۿ֐-׿一-鿿　-〿가-힯ऀ-ॿ]+',
            ' ', text
        )

        # Remove spaces inside parentheses: ( PPP ) → (PPP), ( DST ) → (DST)
        text = re.sub(r'\(\s+', '(', text)
        text = re.sub(r'\s+\)', ')', text)

        # Remove spaces inside square brackets: [ 3 ] already handled above
        # but catch any remaining: [ text ] → [text]
        text = re.sub(r'\[\s+', '[', text)
        text = re.sub(r'\s+\]', ']', text)

        # Fix spaces before numeric superscripts ONLY for known units:
        # km 2 → km2, m 2 → m2 (not "Beirut 33" or "December 1843")
        text = re.sub(r'\b(km|m|sq)\s+(\d)', r'\1\2', text)

        # Fix spaces around + in timezone ONLY for UTC pattern: UTC +2 → UTC+2
        text = re.sub(r'\bUTC\s*\+\s*(\d)', r'UTC+\1', text)
        text = re.sub(r'\bUTC\s*-\s*(\d)', r'UTC-\1', text)

        # Remove trailing/leading punctuation-only fragments (e.g. lone '.' after Arabic stripping)
        text = re.sub(r'\s+[.\s]+$', '', text).strip()

        # Collapse all remaining whitespace
        text = ' '.join(text.split())
        return text.strip()

    # ── Bulk scrape ───────────────────────────────────────────────────────────

    def scrape_multiple_countries(self, country_list: List[str],
                                  force_rescrape: bool = False) -> List[Dict]:
        results = []
        total   = len(country_list)
        skipped = 0

        for i, country in enumerate(country_list, 1):
            print(f"Scraping {i}/{total}: {country}")
            data = self.get_country_infobox(country, force_rescrape=force_rescrape)

            if data:
                results.append(data)
            elif self.country_exists_in_db(country):
                skipped += 1
            else:
                print(f"❌ Failed to scrape: {country}")

            time.sleep(1.5)

        print(f"\n{'='*50}")
        print(f"Total successful scrapes : {len(results)}/{total}")
        print(f"Already in DB (skipped)  : {skipped}/{total}")
        print(f"{'='*50}")
        return results


# ── UN country helpers ────────────────────────────────────────────────────────

def get_un_countries() -> List[str]:
    try:
        url     = "https://www.un.org/en/about-us/member-states"
        headers = {'User-Agent': 'Mozilla/5.0 (Educational Project) WikipediaInfoboxScraper/1.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        countries = []
        for heading in soup.find_all('h3', class_='node-title'):
            name = heading.get_text().strip()
            if name:
                countries.append(_normalize_un_country_name(name))

        if not countries:
            member_list = soup.find('div', class_='view-content')
            if member_list:
                for link in member_list.find_all('a'):
                    name = link.get_text().strip()
                    if name and len(name) > 1:
                        countries.append(_normalize_un_country_name(name))

        if countries:
            countries = sorted(list(set(countries)))
            print(f"Fetched {len(countries)} UN member states")
            return countries

        print("Warning: UN website parse failed, using fallback list")
        return get_un_countries_fallback()

    except Exception as e:
        print(f"Error fetching UN countries: {e}")
        return get_un_countries_fallback()


def _normalize_un_country_name(country_name: str) -> str:
    special_cases = {
        'Georgia': 'Georgia_(country)',
        'Congo (Republic of the)': 'Republic_of_the_Congo',
        'Congo (Democratic Republic of the)': 'Democratic_Republic_of_the_Congo',
        "Korea (Democratic People's Republic of)": 'North_Korea',
        'Korea (Republic of)': 'South_Korea',
        'Micronesia (Federated States of)': 'Federated_States_of_Micronesia',
        'Macedonia (the former Yugoslav Republic of)': 'North_Macedonia',
        'North Macedonia': 'North_Macedonia',
        'Cabo Verde': 'Cape_Verde',
        "Côte d'Ivoire": 'Ivory_Coast',
        'Eswatini': 'Eswatini',
        'Timor-Leste': 'East_Timor',
        'Türkiye': 'Turkey',
        'Turkey': 'Turkey',
        'Iran (Islamic Republic of)': 'Iran',
        'Venezuela (Bolivarian Republic of)': 'Venezuela',
        'Bolivia (Plurinational State of)': 'Bolivia',
        'Tanzania, United Republic of': 'Tanzania',
        'Moldova (Republic of)': 'Moldova',
        'Viet Nam': 'Vietnam',
        'Russian Federation': 'Russia',
        'Syrian Arab Republic': 'Syria',
        "Lao People's Democratic Republic": 'Laos',
        'United Kingdom of Great Britain and Northern Ireland': 'United_Kingdom',
        'United States of America': 'United_States',
    }
    return special_cases.get(country_name, country_name.strip())


def get_un_countries_fallback() -> List[str]:
    return [
        "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
        "Antigua_and_Barbuda", "Argentina", "Armenia", "Australia", "Austria",
        "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados",
        "Belarus", "Belgium", "Belize", "Benin", "Bhutan",
        "Bolivia", "Bosnia_and_Herzegovina", "Botswana", "Brazil", "Brunei",
        "Bulgaria", "Burkina_Faso", "Burundi", "Cape_Verde", "Cambodia",
        "Cameroon", "Canada", "Central_African_Republic", "Chad", "Chile",
        "China", "Colombia", "Comoros", "Democratic_Republic_of_the_Congo",
        "Republic_of_the_Congo", "Costa_Rica", "Croatia", "Cuba", "Cyprus",
        "Czech_Republic", "Denmark", "Djibouti", "Dominica", "Dominican_Republic",
        "Ecuador", "Egypt", "El_Salvador", "Equatorial_Guinea", "Eritrea",
        "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France",
        "Gabon", "Gambia", "Georgia_(country)", "Germany", "Ghana",
        "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau",
        "Guyana", "Haiti", "Honduras", "Hungary", "Iceland",
        "India", "Indonesia", "Iran", "Iraq", "Ireland",
        "Israel", "Italy", "Jamaica", "Japan", "Jordan",
        "Kazakhstan", "Kenya", "Kiribati", "North_Korea", "South_Korea",
        "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon",
        "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania",
        "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives",
        "Mali", "Malta", "Marshall_Islands", "Mauritania", "Mauritius",
        "Mexico", "Federated_States_of_Micronesia", "Moldova", "Monaco",
        "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar",
        "Namibia", "Nauru", "Nepal", "Netherlands", "New_Zealand",
        "Nicaragua", "Niger", "Nigeria", "North_Macedonia", "Norway",
        "Oman", "Pakistan", "Palau", "Palestine", "Panama",
        "Papua_New_Guinea", "Paraguay", "Peru", "Philippines", "Poland",
        "Portugal", "Qatar", "Romania", "Russia", "Rwanda",
        "Saint_Kitts_and_Nevis", "Saint_Lucia", "Saint_Vincent_and_the_Grenadines",
        "Samoa", "San_Marino", "Sao_Tome_and_Principe", "Saudi_Arabia",
        "Senegal", "Serbia", "Seychelles", "Sierra_Leone", "Singapore",
        "Slovakia", "Slovenia", "Solomon_Islands", "Somalia", "South_Africa",
        "South_Sudan", "Spain", "Sri_Lanka", "Sudan", "Suriname",
        "Sweden", "Switzerland", "Syria", "Tajikistan", "Tanzania",
        "Thailand", "East_Timor", "Togo", "Tonga", "Trinidad_and_Tobago",
        "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda",
        "Ukraine", "United_Arab_Emirates", "United_Kingdom", "United_States",
        "Uruguay", "Uzbekistan", "Vanuatu", "Venezuela", "Vietnam",
        "Yemen", "Zambia", "Zimbabwe"
    ]