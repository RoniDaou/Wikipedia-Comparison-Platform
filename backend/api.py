"""
Flask API for Wikipedia Infobox Scraper
Provides RESTful endpoints for data collection and comparison
Steps 1-6 integrated
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from scraper import WikipediaInfoboxScraper, get_un_countries
from database import WikipediaDatabase
from tree_builder import DocumentTreeBuilder
from ted_comparator import TEDComparator
from edit_script import EditScriptExtractor
from patcher import PatchingPipeline, TreePatcher, PostProcessor
from clustering import ClusteringPipeline
from bson import ObjectId
import json
import os
import threading
from collections import OrderedDict

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
#  Custom JSON encoder
# ─────────────────────────────────────────────

class MongoJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return super().default(o)

# ─────────────────────────────────────────────
#  Initialize components
# ─────────────────────────────────────────────

db           = WikipediaDatabase()
scraper      = WikipediaInfoboxScraper(database=db)
tree_builder = DocumentTreeBuilder()       # Step 2
comparator   = TEDComparator()             # Step 3
extractor    = EditScriptExtractor()       # Step 4
pipeline     = PatchingPipeline()          # Steps 5 & 6
patcher      = TreePatcher()
processor    = PostProcessor()
clustering_pipeline = ClusteringPipeline(db=db, comparator=comparator)

# ── Matrix build progress state ───────────────────────────────────────────
_matrix_build_state = {
    'running':   False,
    'done':      0,
    'total':     0,
    'last_pair': '',
    'finished':  False,
    'error':     None,
    'matrix_id': None,   # populated when build completes
}

# ─────────────────────────────────────────────
#  Root
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return jsonify({
        'service': 'Wikipedia Infobox API',
        'version': '2.0',
        'status': 'running',
        'endpoints': {
            'health':          '/api/health',
            'countries':       '/api/countries',
            'country':         '/api/country/<country_name>',
            'scrape':          '/api/scrape (POST)',
            'bulk_scrape':     '/api/scrape/bulk (POST)',
            'preprocess':      '/api/preprocess/<country_name> (GET)',
            'preprocess_xml':  '/api/preprocess/<country_name>/xml (GET)',
            'preprocess_both': '/api/preprocess/compare (POST)',
            'compare':         '/api/compare (POST)',
            'edit_script':     '/api/edit-script (POST)',
            'edit_script_xml': '/api/edit-script/xml (POST)',
            'patch':           '/api/patch (POST)',
            'patch_infobox':   '/api/patch/infobox (POST)',
            'statistics':      '/api/statistics',
            'un_countries':    '/api/un-countries'
        }
    })

# ─────────────────────────────────────────────
#  Health
# ─────────────────────────────────────────────

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Wikipedia Infobox API'})

# ─────────────────────────────────────────────
#  Countries
# ─────────────────────────────────────────────

@app.route('/api/countries', methods=['GET'])
def get_countries():
    try:
        countries = db.get_country_names()
        return jsonify({
            'success':   True,
            'countries': sorted(countries),
            'count':     len(countries)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────
#  Step 1 — Scraping
# ─────────────────────────────────────────────

@app.route('/api/scrape', methods=['POST'])
def scrape_country():
    try:
        data           = request.get_json()
        country_name   = data.get('country_name')
        force_rescrape = data.get('force_rescrape', False)

        if not country_name:
            return jsonify({'success': False, 'error': 'Country name required'}), 400

        if not force_rescrape and scraper.country_exists_in_db(country_name):
            normalized_name = scraper._normalize_country_name(country_name)
            display_name    = scraper._format_country_name_for_display(normalized_name)
            return jsonify({
                'success': False,
                'error': f'{display_name} already exists in database. Use force_rescrape to update.'
            }), 409

        infobox_data = scraper.get_country_infobox(country_name, force_rescrape=force_rescrape)

        if not infobox_data:
            return jsonify({'success': False, 'error': 'Failed to scrape country data'}), 404

        db.insert_country(infobox_data)
        infobox_data.pop('_id', None)

        return jsonify({
            'success': True,
            'message': f'Successfully scraped {infobox_data["country_name"]}',
            'data':    infobox_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scrape/bulk', methods=['POST'])
def scrape_bulk():
    try:
        data           = request.get_json()
        country_list   = data.get('countries', [])
        force_rescrape = data.get('force_rescrape', False)

        if not country_list:
            country_list = get_un_countries()

        results       = scraper.scrape_multiple_countries(country_list, force_rescrape=force_rescrape)
        success_count = db.insert_multiple_countries(results)

        return jsonify({
            'success':         True,
            'message':         f'Scraped {success_count}/{len(country_list)} countries',
            'scraped_count':   success_count,
            'total_requested': len(country_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────
#  Step 2 — Pre-processing (Tree Building)
# ─────────────────────────────────────────────

@app.route('/api/preprocess/<country_name>', methods=['GET'])
def preprocess_country(country_name):
    """Build and return the document tree for a single country."""
    try:
        print(f"\n[PREPROCESS] ========== PREPROCESS COUNTRY ==========")
        print(f"[PREPROCESS] Country: {country_name}")
        
        country_data = db.get_country(country_name)
        
        if not country_data:
            print(f"[PREPROCESS] Not in countries collection, checking edited...")
            country_data = db.get_edited_tree(country_name)
            if country_data:
                print(f"[PREPROCESS] ✅ Found in edited collection")
                country_data.pop('_id', None)
        
        if not country_data:
            print(f"[PREPROCESS] ❌ Country not found in database")
            return jsonify({'success': False,
                            'error': f'{country_name} not found in database'}), 404

        country_data.pop('_id', None)
        
        print(f"[PREPROCESS] Building tree...")
        print(f"[PREPROCESS] Fields keys: {list(country_data.get('fields', {}).keys())[:5]}...")
        
        root  = tree_builder.build_tree(country_data)
        stats = tree_builder.get_stats(root)
        
        print(f"[PREPROCESS] ✅ Tree built with {stats.get('total_nodes', 0)} nodes")
        print(f"[PREPROCESS] ==========================================\n")

        return jsonify({
            'success': True,
            'country': country_data['country_name'],
            'tree':    tree_builder.tree_to_dict(root),
            'xml':     tree_builder.tree_to_xml(root),
            'stats':   stats
        })
    except Exception as e:
        print(f"[PREPROCESS] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/preprocess/<country_name>/xml', methods=['GET'])
def preprocess_country_xml(country_name):
    """Download the document tree as an XML file."""
    try:
        country_data = db.get_country(country_name)
        if not country_data:
            return jsonify({'success': False,
                            'error': f'{country_name} not found in database'}), 404

        country_data.pop('_id', None)

        root    = tree_builder.build_tree(country_data)
        xml_str = tree_builder.tree_to_xml(root)

        return app.response_class(
            response=xml_str,
            status=200,
            mimetype='application/xml',
            headers={
                'Content-Disposition':
                    f'attachment; filename="{country_name}_tree.xml"'
            }
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preprocess/compare', methods=['POST'])
def preprocess_compare():
    """Build and return document trees for two countries."""
    try:
        data          = request.get_json()
        country1_name = data.get('country1')
        country2_name = data.get('country2')

        if not country1_name or not country2_name:
            return jsonify({'success': False,
                            'error': 'Both country1 and country2 required'}), 400

        country1_data = db.get_country(country1_name)
        country2_data = db.get_country(country2_name)

        if not country1_data:
            return jsonify({'success': False,
                            'error': f'{country1_name} not found'}), 404
        if not country2_data:
            return jsonify({'success': False,
                            'error': f'{country2_name} not found'}), 404

        country1_data.pop('_id', None)
        country2_data.pop('_id', None)

        tree1 = tree_builder.build_tree(country1_data)
        tree2 = tree_builder.build_tree(country2_data)

        return jsonify({
            'success': True,
            'country1': {
                'name':  country1_data['country_name'],
                'tree':  tree_builder.tree_to_dict(tree1),
                'xml':   tree_builder.tree_to_xml(tree1),
                'stats': tree_builder.get_stats(tree1),
            },
            'country2': {
                'name':  country2_data['country_name'],
                'tree':  tree_builder.tree_to_dict(tree2),
                'xml':   tree_builder.tree_to_xml(tree2),
                'stats': tree_builder.get_stats(tree2),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────
#  Steps 3 & 4 — TED Comparison + Edit Script
# ─────────────────────────────────────────────

@app.route('/api/compare', methods=['POST'])
def compare_countries():
    """Steps 3 & 4 — Compare two countries/comparisons using TED and return edit script."""
    try:
        data          = request.get_json()
        country1_name = data.get('country1')
        country2_name = data.get('country2')

        if not country1_name or not country2_name:
            return jsonify({'success': False,
                            'error': 'Both country names required'}), 400

        print(f"\n{'='*70}")
        print(f"[COMPARE] Starting comparison: {country1_name} vs {country2_name}")
        print(f"{'='*70}")

        # ✅ TRY TO GET country1 - check countries FIRST, then editedcountries
        country1_data = db.get_country(country1_name)
        if not country1_data:
            print(f"[COMPARE] Not found in countries, checking editedcountries...")
            country1_data = db.get_edited_tree(country1_name)
            if country1_data:
                print(f"[COMPARE] ✅ Found in editedcountries")
        
        # ✅ TRY TO GET country2 - check countries FIRST, then editedcountries
        country2_data = db.get_country(country2_name)
        if not country2_data:
            print(f"[COMPARE] Not found in countries, checking editedcountries...")
            country2_data = db.get_edited_tree(country2_name)
            if country2_data:
                print(f"[COMPARE] ✅ Found in editedcountries")

        if not country1_data:
            return jsonify({'success': False,
                            'error': f'{country1_name} not found'}), 404
        if not country2_data:
            return jsonify({'success': False,
                            'error': f'{country2_name} not found'}), 404

        country1_data.pop('_id', None)
        country2_data.pop('_id', None)

        # Step 3: TED
        result = comparator.compare_countries(country1_data, country2_data)

        # Step 4: Edit script
        es      = extractor.extract(result)
        es_dict = es.to_dict()

        # Report (no auto-save)
        report = comparator.generate_report(result)

        # Count only completed comparisons. The increment is persistent and atomic.
        total_comparisons = db.record_comparisons(1)

        return app.response_class(
            response=json.dumps({
                'success':     True,
                'comparison':  result,
                'edit_script': es_dict,
                'report':      report,
                'total_comparisons': total_comparisons
            }, cls=MongoJSONEncoder),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/compare-all', methods=['POST'])
def compare_all_countries():
    """Compare one country against all countries in the database.
    Returns: List of comparisons sorted by similarity (most to least similar)
    """
    try:
        data = request.get_json()
        base_country_name = data.get('base_country')
        
        if not base_country_name:
            return jsonify({'success': False, 'error': 'Base country name required'}), 400
        
        # Get the base country
        base_country_data = db.get_country(base_country_name)
        if not base_country_data:
            base_country_data = db.get_comparison_by_name(base_country_name)
            if base_country_data:
                base_country_data.pop('saved_at', None)
        
        if not base_country_data:
            return jsonify({'success': False, 
                          'error': f'{base_country_name} not found'}), 404
        
        base_country_data.pop('_id', None)
        
        all_country_names = db.get_country_names()
        all_comparisons = db.get_all_comparisons()
        
        results = []
        
        # Compare base country with all countries
        for country_name in all_country_names:
            if country_name.lower() == base_country_name.lower():
                continue
            
            try:
                other_country_data = db.get_country(country_name)
                if not other_country_data:
                    continue
                
                other_country_data.pop('_id', None)
                
                # Perform comparison
                comparison_result = comparator.compare_countries(base_country_data, other_country_data)
                
                # ✅ FIX: Use similarity_score instead of similarity
                similarity = comparison_result.get('similarity_score', 0)
                
                results.append({
                    'country': country_name,
                    'ted_distance': comparison_result.get('ted_distance', 0),
                    'similarity': similarity
                })
            except Exception as e:
                continue
        
        # Compare base country with all saved comparisons
        for comparison in all_comparisons:
            try:
                comparison_data = db.get_comparison_by_name(comparison)
                if not comparison_data:
                    continue
                
                comparison_data.pop('_id', None)
                comparison_data.pop('saved_at', None)
                
                # Perform comparison
                comparison_result = comparator.compare_countries(base_country_data, comparison_data)
                
                # ✅ FIX: Use similarity_score instead of similarity
                similarity = comparison_result.get('similarity_score', 0)
                
                results.append({
                    'country': comparison,
                    'ted_distance': comparison_result.get('ted_distance', 0),
                    'similarity': similarity
                })
            except Exception as e:
                continue
        
        # Sort by similarity (descending)
        results.sort(key=lambda x: x['similarity'], reverse=True)

        # Count every successfully completed pair in the 1-vs-all operation.
        total_comparisons_made = db.record_comparisons(len(results))
        
        return app.response_class(
            response=json.dumps({
                'success': True,
                'base_country': base_country_name,
                'total_comparisons': len(results),
                'comparison_count': total_comparisons_made,
                'results': results
            }, cls=MongoJSONEncoder),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/comparisons/save', methods=['POST'])
def save_comparison_by_name():
    """Save patched comparison result with custom country_name to comparisons table."""
    try:
        data = request.get_json()
        country_name = data.get('country_name')
        patched_json = data.get('patched_json')
        
        if not country_name:
            return jsonify({'success': False, 'error': 'Country name required'}), 400
        
        if not patched_json:
            return jsonify({'success': False, 'error': 'Patched JSON required'}), 400
        
        # Check if country_name is unique in comparisons
        if db.comparison_country_name_exists(country_name):
            return jsonify({
                'success': False, 
                'error': f'Comparison with country name "{country_name}" already exists. Please choose a different name.'
            }), 409
        
        # Save the comparison with the custom country_name
        db.save_comparison_with_country_name(country_name, patched_json)
        
        return jsonify({
            'success': True, 
            'message': f'Comparison saved as "{country_name}"'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────
#  Tree Editing and Storage
# ─────────────────────────────────────────────

@app.route('/api/save-edited-tree', methods=['POST'])
def save_edited_tree():
    """Save edited tree with field order preserved in MongoDB."""
    try:
        data = request.get_json()
        original_country = data.get('original_country')
        edited_tree = data.get('edited_tree')
        
        print(f"\n{'='*70}")
        print(f"[SAVE_EDITED_TREE] ========== SAVE EDITED TREE ==========")
        print(f"[SAVE_EDITED_TREE] Original country: {original_country}")
        
        if not original_country or not edited_tree:
            return jsonify({'success': False, 'error': 'Missing required data'}), 400
        
        # ✅ GET THE ORIGINAL DOCUMENT TO CAPTURE ITS FIELD ORDER
        print(f"[SAVE_EDITED_TREE] Fetching original document...")
        original_doc = db.get_country(original_country)
        
        original_field_order = []
        if original_doc:
            if '_field_order' in original_doc:
                original_field_order = original_doc['_field_order']
            else:
                # Extract from fields dict in order
                original_field_order = list(original_doc.get('fields', {}).keys())
            
            print(f"[SAVE_EDITED_TREE] Original field order (first 10):")
            for i, field in enumerate(original_field_order[:10]):
                print(f"[SAVE_EDITED_TREE]   [{i+1}] {field}")
        
        # Find highest number
        existing = list(db.editedcountries.find(
            {'country_name': {'$regex': f'^{original_country}_\\d+$'}}
        ))
        
        next_num = 1
        if existing:
            numbers = []
            for doc in existing:
                try:
                    num = int(doc['country_name'].split('_')[-1])
                    numbers.append(num)
                except:
                    pass
            if numbers:
                next_num = max(numbers) + 1
        
        new_country_name = f"{original_country}_{next_num}"
        edited_tree['country_name'] = new_country_name
        
        print(f"[SAVE_EDITED_TREE] New country name: {new_country_name}")
        
        # ✅ FILTER ORIGINAL ORDER TO ONLY INCLUDE FIELDS THAT STILL EXIST
        print(f"[SAVE_EDITED_TREE] Filtering original order...")
        filtered_field_order = [field for field in original_field_order if field in edited_tree.get('fields', {})]
        
        print(f"[SAVE_EDITED_TREE] Original: {len(original_field_order)} → After filtering: {len(filtered_field_order)} fields")
        print(f"[SAVE_EDITED_TREE] Final field order (first 10):")
        for i, field in enumerate(filtered_field_order[:10]):
            print(f"[SAVE_EDITED_TREE]   [{i+1}] {field}")
        
        # ✅ REBUILD ORDERED DICT
        print(f"[SAVE_EDITED_TREE] Rebuilding ordered fields dict.")
        ordered_fields = OrderedDict()

        for field_name in filtered_field_order:
            if field_name in edited_tree.get('fields', {}):
                ordered_fields[field_name] = edited_tree['fields'][field_name]

        # In case a newly added field exists but was not in the original order
        for field_name, field_value in edited_tree.get('fields', {}).items():
            if field_name not in ordered_fields:
                ordered_fields[field_name] = field_value
                filtered_field_order.append(field_name)

        edited_tree['fields'] = ordered_fields
        edited_tree['_field_order'] = list(ordered_fields.keys())

        print(f"[SAVE_EDITED_TREE] Storing as ordered fields dict with {len(ordered_fields)} items")
        print(f"[SAVE_EDITED_TREE] Inserting into database...")
        
        db.editedcountries.insert_one(edited_tree)
        print(f"[SAVE_EDITED_TREE] ✅ Successfully inserted {new_country_name}")
        print(f"{'='*70}\n")
        
        return jsonify({
            'success': True,
            'saved_name': new_country_name,
            'message': f'Saved as {new_country_name}'
        })
    except Exception as e:
        print(f"[SAVE_EDITED_TREE] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500  

@app.route('/api/edited-countries', methods=['GET'])
def get_edited_countries():
    """Get all edited countries."""
    try:
        edited_names = db.get_all_edited_countries()
        
        print(f"\n[GET_EDITED_COUNTRIES] Found {len(edited_names)} edited countries")
        for i, name in enumerate(edited_names):
            print(f"[GET_EDITED_COUNTRIES]   [{i+1}] {name}")
        
        edited_data = []
        for name in edited_names:
            print(f"\n[GET_EDITED_COUNTRIES] Retrieving: {name}")
            tree = db.get_edited_tree(name)
            
            if tree:
                print(f"[GET_EDITED_COUNTRIES] ✅ Retrieved {name}")
                print(f"[GET_EDITED_COUNTRIES] Tree keys: {list(tree.keys())}")
                edited_data.append(tree)
            else:
                print(f"[GET_EDITED_COUNTRIES] ❌ Failed to retrieve {name}")
        
        print(f"\n[GET_EDITED_COUNTRIES] Final response: {len(edited_data)} items")
        for i, item in enumerate(edited_data):
            print(f"[GET_EDITED_COUNTRIES]   [{i+1}] {item.get('country_name')}")
        
        response = json.dumps(edited_data, cls=MongoJSONEncoder)
        print(f"[GET_EDITED_COUNTRIES] Response size: {len(response)} chars\n")
        
        return app.response_class(
            response=response,
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        print(f"[GET_EDITED_COUNTRIES] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def get_edited_tree(self, tree_name):
    """Get a specific edited tree and restore field order."""
    print(f"\n[GET_EDITED] ========== GET EDITED TREE ==========")
    print(f"[GET_EDITED] Looking for: {tree_name}")

    result = self.editedcountries.find_one({'country_name': tree_name})

    if not result:
        print(f"[GET_EDITED] ❌ Tree not found in database")
        print(f"[GET_EDITED] ==========================================\n")
        return None

    print(f"[GET_EDITED] ✅ Found tree: {result.get('country_name')}")

    # ✅ RESTORE FIELD ORDER FROM _field_order
    fields = result.get('fields', {})
    if isinstance(fields, dict) and '_field_order' in result:
        print(f"[GET_EDITED] Restoring field order from _field_order...")
        ordered_fields = OrderedDict()
        for key in result['_field_order']:
            if key in fields:
                ordered_fields[key] = fields[key]

        # Add any new fields not in _field_order
        for key, value in fields.items():
            if key not in ordered_fields:
                ordered_fields[key] = value

        result['fields'] = ordered_fields
        print(f"[GET_EDITED] ✅ Reordered {len(ordered_fields)} fields")

    result['_id'] = str(result['_id'])
    print(f"[GET_EDITED] ==========================================\n")
    return result

@app.route('/api/country/<country_name>', methods=['GET'])
def get_single_country(country_name):
    """Get a single country (checks countries first, then editedcountries)."""
    try:
        print(f"\n[GET_COUNTRY_ENDPOINT] Looking for: {country_name}")
        
        # Try countries collection first (with normalization)
        data = db.get_country(country_name)
        
        # If not found in countries, try editedcountries WITHOUT normalizing
        if not data:
            print(f"[GET_COUNTRY_ENDPOINT] Not in countries, checking editedcountries with EXACT name...")
            data = db.editedcountries.find_one({'country_name': country_name})
            if data:
                print(f"[GET_COUNTRY_ENDPOINT] ✅ Found in editedcountries")
                
                # Restore field order if present
                fields = data.get('fields', {})
                if isinstance(fields, dict) and '_field_order' in data:
                    ordered_fields = OrderedDict()
                    for key in data['_field_order']:
                        if key in fields:
                            ordered_fields[key] = fields[key]
                    for key, value in fields.items():
                        if key not in ordered_fields:
                            ordered_fields[key] = value
                    data['fields'] = ordered_fields
        
        if not data:
            print(f"[GET_COUNTRY_ENDPOINT] ❌ Not found anywhere")
            return jsonify({'success': False, 'error': f'{country_name} not found'}), 404
        
        data.pop('_id', None)
        print(f"[GET_COUNTRY_ENDPOINT] ✅ Returning data with {len(data.get('fields', {}))} fields")
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        print(f"[GET_COUNTRY_ENDPOINT] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/comparisons', methods=['GET'])
def get_all_comparisons():
    """Get all saved comparisons (names only)."""
    try:
        comparisons = db.get_all_comparisons()
        return jsonify({
            'success': True,
            'comparisons': comparisons
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/comparison/<comparison_name>', methods=['GET'])
def get_comparison_by_name(comparison_name):
    """Get a specific comparison by country_name."""
    try:
        comparison = db.get_comparison_by_name(comparison_name)
        if comparison:
            comparison.pop('_id', None)
            return jsonify({'success': True, 'data': comparison})
        else:
            return jsonify({'success': False, 'error': 'Comparison not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
  

@app.route('/api/edit-script', methods=['POST'])
def get_edit_script():
    """Step 4 — Return the edit script for two countries (JSON or XML)."""
    try:
        data          = request.get_json()
        country1_name = data.get('country1')
        country2_name = data.get('country2')
        fmt           = data.get('format', 'json')

        if not country1_name or not country2_name:
            return jsonify({'success': False,
                            'error': 'Both country names required'}), 400

        country1_data = db.get_country(country1_name)
        country2_data = db.get_country(country2_name)

        if not country1_data:
            return jsonify({'success': False,
                            'error': f'{country1_name} not found'}), 404
        if not country2_data:
            return jsonify({'success': False,
                            'error': f'{country2_name} not found'}), 404

        country1_data.pop('_id', None)
        country2_data.pop('_id', None)

        result = comparator.compare_countries(country1_data, country2_data)
        es     = extractor.extract(result)

        if fmt == 'xml':
            return app.response_class(
                response=es.to_xml(),
                status=200,
                mimetype='application/xml',
                headers={
                    'Content-Disposition':
                        f'attachment; filename="{country1_name}_{country2_name}_edit_script.xml"'
                }
            )

        return jsonify({
            'success':     True,
            'edit_script': es.to_dict(),
            'summary':     es.summary()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/edit-script/xml', methods=['POST'])
def get_edit_script_xml():
    """Step 4 — Download the edit script as XML."""
    try:
        data          = request.get_json()
        country1_name = data.get('country1')
        country2_name = data.get('country2')

        if not country1_name or not country2_name:
            return jsonify({'success': False,
                            'error': 'Both country names required'}), 400

        country1_data = db.get_country(country1_name)
        country2_data = db.get_country(country2_name)

        if not country1_data or not country2_data:
            return jsonify({'success': False, 'error': 'Country not found'}), 404

        country1_data.pop('_id', None)
        country2_data.pop('_id', None)

        result = comparator.compare_countries(country1_data, country2_data)
        es     = extractor.extract(result)

        return app.response_class(
            response=es.to_xml(),
            status=200,
            mimetype='application/xml',
            headers={
                'Content-Disposition':
                    f'attachment; filename="{country1_name}_{country2_name}_edit_script.xml"'
            }
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────
#  Steps 5 & 6 — Patching + Post-processing
# ─────────────────────────────────────────────

@app.route('/api/patch', methods=['POST'])
def patch_countries():
    """Steps 5 & 6 — Patch T1 into T2 and return post-processed output."""
    try:
        data = request.get_json()
        country1_name = data.get('country1')
        country2_name = data.get('country2')
        fmt = data.get('format', 'all')

        if not country1_name or not country2_name:
            return jsonify({'success': False,
                            'error': 'Both country names required'}), 400

        country1_data = db.get_country(country1_name)
        if not country1_data:
            country1_data = db.get_edited_tree(country1_name)
            if country1_data:
                country1_data.pop('_id', None)
        
        country2_data = db.get_country(country2_name)
        if not country2_data:
            country2_data = db.get_edited_tree(country2_name)
            if country2_data:
                country2_data.pop('_id', None)

        if not country1_data:
            return jsonify({'success': False,
                            'error': f'{country1_name} not found'}), 404
        if not country2_data:
            return jsonify({'success': False,
                            'error': f'{country2_name} not found'}), 404

        country1_data.pop('_id', None)
        country2_data.pop('_id', None)

        result = pipeline.run(country1_data, country2_data)

        if fmt == 'xml':
            return app.response_class(
                response=result['xml'],
                status=200,
                mimetype='application/xml',
                headers={
                    'Content-Disposition':
                        f'attachment; filename="{country1_name}_{country2_name}_patched.xml"'
                }
            )
        elif fmt == 'infobox':
            return jsonify({'success': True, 'infobox': result['infobox']})
        elif fmt == 'json':
            return jsonify({'success': True, 'json_doc': result['json_doc']})
        else:
            return app.response_class(
                response=json.dumps({
                    'success':        True,
                    'source_country': result['source_country'],
                    'target_country': result['target_country'],
                    'ted_distance':   result['ted_distance'],
                    'similarity':     result['similarity'],
                    'edit_script':    result['edit_script'],
                    'patched_tree':   result['patched_tree'],
                    'xml':            result['xml'],
                    'json_doc':       result['json_doc'],
                    'infobox':        result['infobox'],
                }, cls=MongoJSONEncoder),
                status=200,
                mimetype='application/json'
            )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/patch/infobox', methods=['POST'])
def patch_to_infobox():
    """Steps 5 & 6 — Return patched result as Wikipedia infobox text."""
    try:
        data          = request.get_json()
        country1_name = data.get('country1')
        country2_name = data.get('country2')

        if not country1_name or not country2_name:
            return jsonify({'success': False,
                            'error': 'Both country names required'}), 400

        country1_data = db.get_country(country1_name)
        country2_data = db.get_country(country2_name)

        if not country1_data or not country2_data:
            return jsonify({'success': False, 'error': 'Country not found'}), 404

        country1_data.pop('_id', None)
        country2_data.pop('_id', None)

        result = pipeline.run(country1_data, country2_data)

        return jsonify({
            'success':        True,
            'source_country': result['source_country'],
            'target_country': result['target_country'],
            'ted_distance':   result['ted_distance'],
            'similarity':     result['similarity'],
            'infobox':        result['infobox'],
            'json_doc':       result['json_doc'],
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────
#  Statistics & UN countries
# ─────────────────────────────────────────────

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    try:
        stats = db.get_statistics()
        return jsonify({'success': True, 'statistics': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/un-countries', methods=['GET'])
def get_un_countries_list():
    try:
        countries = get_un_countries()
        return jsonify({
            'success':   True,
            'countries': countries,
            'count':     len(countries)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cluster/features', methods=['GET'])
def get_cluster_features():
    """
    Return available infobox field names for the currently selected countries.

    Query params:
        ?countries=Lebanon&countries=France

    If no countries are provided, the endpoint falls back to all stored countries.
    This keeps the UI flow country-first: users choose countries, then choose
    which fields inside those countries should be used for TED.
    """
    try:
        requested_countries = request.args.getlist('countries')

        # Backward-compatible fallback for comma-separated calls.
        if not requested_countries:
            raw = request.args.get('countries', '')
            if raw:
                requested_countries = [c.strip() for c in raw.split(',') if c.strip()]

        country_names = requested_countries or db.get_country_names()

        features = set()
        valid_country_count = 0

        for country_name in country_names:
            doc = db.get_country(country_name)
            if not doc:
                doc = db.get_edited_tree(country_name)
            if not doc:
                continue

            valid_country_count += 1
            fields = doc.get('fields', {}) or {}
            for field_name in fields.keys():
                if field_name:
                    features.add(str(field_name))

        return jsonify({
            'success': True,
            'features': sorted(features, key=lambda x: x.lower()),
            'count': len(features),
            'country_count': valid_country_count,
            'countries_scope': country_names
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────
#  Error handlers
# ═══════════════════════════════════════════════════════════════════════════
#  Clustering routes
# ═══════════════════════════════════════════════════════════════════════════

# ── Similarity Matrix — list / get / build / delete ──────────────────────

@app.route('/api/cluster/matrices', methods=['GET'])
def list_matrices():
    """List all stored similarity matrices (metadata only, no matrix values)."""
    try:
        matrices = db.list_similarity_matrices()
        return jsonify({'success': True, 'matrices': matrices})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cluster/matrix/<matrix_id>', methods=['GET'])
def get_matrix(matrix_id):
    """Return the full similarity matrix document by _id."""
    try:
        doc = db.get_similarity_matrix(matrix_id)
        if not doc:
            return jsonify({'success': False, 'error': 'Matrix not found'}), 404
        return jsonify({'success': True, 'matrix': doc})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cluster/matrix/<matrix_id>', methods=['DELETE'])
def delete_matrix(matrix_id):
    """Delete one similarity matrix by _id."""
    try:
        deleted = db.delete_similarity_matrix(matrix_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Matrix not found'}), 404
        return jsonify({'success': True, 'message': f'Matrix {matrix_id} deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cluster/build-matrix', methods=['POST'])
def build_similarity_matrix():
    """
    Trigger computation of a new similarity matrix.
    Always creates a new document — never overwrites existing ones.

    Body (JSON):
        {
            "countries":  ["Lebanon", "France", ...],  // null = all in DB
            "name":       "My Middle East set",        // optional label
            "matrix_mode": "full_ted" | "feature_ted", // optional
            "features":   ["population", "area", ...], // required for feature_ted
            "incremental_from": "<matrix_id>"           // full_ted only
        }
    """
    global _matrix_build_state

    if _matrix_build_state['running']:
        return jsonify({'success': False,
                        'error':   'Matrix build already in progress.'}), 409

    data           = request.get_json() or {}
    country_names  = data.get('countries')
    name           = data.get('name', '')
    incr_from      = data.get('incremental_from', '')   # _id of base matrix
    matrix_mode    = data.get('matrix_mode', 'full_ted')
    selected_features = data.get('features') or data.get('selected_features') or []

    if matrix_mode not in ('full_ted', 'feature_ted'):
        return jsonify({'success': False,
                        'error': 'matrix_mode must be "full_ted" or "feature_ted"'}), 400
    if matrix_mode == 'feature_ted' and not selected_features:
        return jsonify({'success': False,
                        'error': 'Select at least one feature for feature-filtered TED clustering.'}), 400
    if matrix_mode == 'feature_ted' and incr_from:
        return jsonify({'success': False,
                        'error': 'Incremental extension is only supported for full TED matrices.'}), 400

    def _progress(done, total, pair_info):
        _matrix_build_state.update(done=done, total=total, last_pair=pair_info)

    def _build():
        global _matrix_build_state
        _matrix_build_state.update(running=True, done=0, total=0,
                                    last_pair='', finished=False,
                                    error=None, matrix_id=None)
        try:
            if incr_from:
                doc = clustering_pipeline.build_incremental(
                    incr_from, name=name, progress_callback=_progress)
            else:
                doc = clustering_pipeline.build_and_save_matrix(
                    country_names=country_names,
                    name=name,
                    progress_callback=_progress,
                    selected_features=selected_features if matrix_mode == 'feature_ted' else None)
            _matrix_build_state.update(finished=True, matrix_id=doc.get('_id'))
        except Exception as exc:
            _matrix_build_state.update(error=str(exc))
        finally:
            _matrix_build_state['running'] = False

    threading.Thread(target=_build, daemon=True).start()
    return jsonify({
        'success': True,
        'message': 'Matrix build started in background.',
        'poll':    '/api/cluster/matrix-status'
    })


@app.route('/api/cluster/matrix-status', methods=['GET'])
def matrix_status():
    """Return current build progress."""
    return jsonify({
        'success':     True,
        'build_state': dict(_matrix_build_state)
    })


# ── Cluster Results — list / get / run / delete ───────────────────────────

@app.route('/api/cluster/results', methods=['GET'])
def list_cluster_results():
    """
    List all stored cluster results (metadata only).
    Query params:
        ?algorithm=kmeans|agglomerative   // optional filter
    """
    try:
        algorithm = request.args.get('algorithm', '')
        results   = db.list_cluster_results(algorithm)
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cluster/result/<result_id>', methods=['GET'])
def get_cluster_result(result_id):
    """Return the full cluster result document by _id."""
    try:
        doc = db.get_cluster_result(result_id)
        if not doc:
            return jsonify({'success': False, 'error': 'Result not found'}), 404
        return jsonify({'success': True, 'result': doc})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cluster/result/<result_id>', methods=['DELETE'])
def delete_cluster_result(result_id):
    """Delete one cluster result by _id."""
    try:
        deleted = db.delete_cluster_result(result_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Result not found'}), 404
        return jsonify({'success': True, 'message': f'Result {result_id} deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cluster/run', methods=['POST'])
def run_clustering():
    """
    Run a clustering algorithm on a specific saved matrix.

    Body (JSON):
        {
            "algorithm":  "kmeans" | "agglomerative",  // required
            "matrix_id":  "<_id>",                         // required
            "name":       "My run label",                   // optional

            // K-Medoids params
            "k":         3,
            "max_iter":  100,
            "n_init":    10,

            // Agglomerative params
            "n_clusters": 3,
            "linkage":    "average"  // average | single | complete
        }
    """
    try:
        data      = request.get_json() or {}
        algorithm = data.get('algorithm', 'kmeans').lower()
        matrix_id = data.get('matrix_id', '')
        name      = data.get('name', '')

        if algorithm not in ('kmeans', 'agglomerative'):
            return jsonify({'success': False,
                            'error': 'algorithm must be "kmeans" or "agglomerative"'}), 400
        if not matrix_id:
            return jsonify({'success': False,
                            'error': 'matrix_id is required'}), 400

        matrix_doc = db.get_similarity_matrix(matrix_id)
        if not matrix_doc:
            return jsonify({'success': False,
                            'error': f'Matrix {matrix_id} not found'}), 404
        if matrix_doc.get('count', 0) < 2:
            return jsonify({'success': False,
                            'error': 'Matrix has fewer than 2 countries'}), 400

        if algorithm == 'kmeans':
            k        = int(data.get('k', 3))
            max_iter = int(data.get('max_iter', 100))
            n_init   = int(data.get('n_init', 10))
            if k < 1:
                return jsonify({'success': False, 'error': 'k must be ≥ 1'}), 400
            if k > matrix_doc['count']:
                return jsonify({'success': False,
                                'error': f'k={k} > available countries ({matrix_doc["count"]})'}), 400
            if max_iter < 1:
                return jsonify({
                    'success': False,
                    'error': 'max_iter must be >= 1'
                }), 400

            if n_init < 1:
                return jsonify({
                    'success': False,
                    'error': 'n_init must be >= 1'
                }), 400
            result = clustering_pipeline.run_kmeans(
                matrix_doc, k=k, max_iter=max_iter, n_init=n_init, name=name)
        else:
            auto_cut   = bool(data.get('auto_cut', False))
            linkage    = data.get('linkage', 'average')
            if linkage not in ('average', 'single', 'complete'):
                return jsonify({'success': False,
                                'error': 'linkage must be "average", "single", or "complete"'}), 400

            if auto_cut:
                n_clusters = None
            else:
                n_clusters = int(data.get('n_clusters', data.get('k', 3)))
                if n_clusters < 1:
                    return jsonify({'success': False, 'error': 'n_clusters must be ≥ 1'}), 400
                if n_clusters > matrix_doc['count']:
                    return jsonify({'success': False,
                                    'error': f'n_clusters={n_clusters} > available countries ({matrix_doc["count"]})'}), 400

            result = clustering_pipeline.run_agglomerative(
                matrix_doc, n_clusters=n_clusters, linkage=linkage,
                name=name, auto_cut=auto_cut)

        return jsonify({'success': True, 'result': result})

    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500



@app.route('/api/cluster/recut', methods=['POST'])
def recut_agglomerative():
    """
    Re-apply a different cut to an existing agglomerative result.
    Does NOT re-run the full algorithm — replays the stored merge_history
    at a new cut point, then returns updated cluster assignments.

    Body (JSON):
        {
            "result_id":  "<_id of saved cluster result>",
            "cut_step":   42,          // number of merges to keep
            "name":       "optional"   // label for the new saved result
        }
    """
    try:
        data      = request.get_json() or {}
        result_id = data.get('result_id', '')
        cut_step  = data.get('cut_step')
        name      = data.get('name', '')

        if not result_id:
            return jsonify({'success': False, 'error': 'result_id is required'}), 400
        if cut_step is None:
            return jsonify({'success': False, 'error': 'cut_step is required'}), 400

        cut_step = int(cut_step)
        existing = db.get_cluster_result(result_id)
        if not existing:
            return jsonify({'success': False, 'error': 'Result not found'}), 404
        if existing.get('algorithm') != 'agglomerative':
            return jsonify({'success': False,
                            'error': 'recut only works on agglomerative results'}), 400

        history = existing.get('merge_history') or existing.get('dendrogram') or []
        if not history:
            return jsonify({'success': False, 'error': 'No merge history in result'}), 400

        n = existing.get('n_countries', 0)
        if n == 0:
            return jsonify({'success': False, 'error': 'n_countries missing from result'}), 400

        cut_step = max(0, min(cut_step, len(history)))

        # Replay merges up to cut_step
        clusters = {i: [i] for i in range(n)}
        next_id  = n
        countries_list = list(existing.get('labels', {}).keys())

        for merge in history[:cut_step]:
            a_id = int(merge['left'])
            b_id = int(merge['right'])
            merged = clusters.pop(a_id, []) + clusters.pop(b_id, [])
            clusters[next_id] = merged
            next_id += 1

        final_clusters = sorted(clusters.values(), key=lambda m: (min(m), len(m)))
        n_clusters_actual = len(final_clusters)

        # Build labels and cluster dicts
        labels = {}
        clusters_out = {}
        for cidx, members in enumerate(final_clusters):
            member_names = [countries_list[i] for i in members if i < len(countries_list)]
            rep = member_names[0] if member_names else ''
            clusters_out[str(cidx)] = {
                'id': cidx,
                'representative': rep,
                'members': member_names,
                'size': len(member_names),
                'centroid': existing.get('clusters', {}).get(str(cidx), {}).get('centroid', [0, 0])
            }
            for name_c in member_names:
                labels[name_c] = cidx

        result_out = dict(existing)
        result_out.pop('_id', None)
        result_out['n_clusters'] = n_clusters_actual
        result_out['cut_step']   = cut_step
        result_out['labels']     = labels
        result_out['clusters']   = clusters_out
        result_out['auto_cut']   = False
        result_out['recut_from'] = result_id

        # Optional: save the recut result as a new DB entry
        save = bool(data.get('save', False))
        save_name = data.get('save_name', '').strip()
        if save:
            matrix_id = existing.get('matrix_id', '')
            if not save_name:
                save_name = (f"AGGLOMERATIVE — k={n_clusters_actual} "
                             f"— {existing.get('n_countries', n)} countries (recut)")
            inserted_id = db.save_cluster_result(
                result_out, name=save_name, matrix_id=matrix_id)
            result_out['_id'] = inserted_id

        return app.response_class(
            response=json.dumps({'success': True, 'result': result_out, 'saved': save},
                                cls=MongoJSONEncoder),
            status=200,
            mimetype='application/json'
        )
    except Exception as exc:
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(exc)}), 500

# ── Exploration helpers ───────────────────────────────────────────────────

@app.route('/api/cluster/neighbors/<country_name>', methods=['GET'])
def get_neighbors(country_name):
    """
    Top-N most similar countries to country_name within a given matrix.
    Query params: ?matrix_id=<_id>&top=5
    """
    try:
        matrix_id  = request.args.get('matrix_id', '')
        top_n      = int(request.args.get('top', 5))
        matrix_doc = db.get_similarity_matrix(matrix_id) if matrix_id \
                     else db.get_latest_similarity_matrix()
        if not matrix_doc:
            return jsonify({'success': False, 'error': 'No matrix available.'}), 400

        neighbors = clustering_pipeline.get_country_neighbors(
            matrix_doc, country_name, top_n=top_n)
        if not neighbors:
            return jsonify({'success': False,
                            'error': f'{country_name} not in matrix'}), 404
        return jsonify({'success': True, 'country': country_name,
                        'neighbors': neighbors})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/cluster/top-pairs', methods=['GET'])
def get_top_pairs():
    """
    Top-N most similar country pairs globally.
    Query params: ?matrix_id=<_id>&top=10
    """
    try:
        matrix_id  = request.args.get('matrix_id', '')
        top_n      = int(request.args.get('top', 10))
        matrix_doc = db.get_similarity_matrix(matrix_id) if matrix_id \
                     else db.get_latest_similarity_matrix()
        if not matrix_doc:
            return jsonify({'success': False, 'error': 'No matrix available.'}), 400

        pairs = clustering_pipeline.get_top_similar_pairs(matrix_doc, top_n=top_n)
        return jsonify({'success': True, 'pairs': pairs})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


# ─────────────────────────────────────────────
#  Error handlers
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error':   'Not Found',
        'message': 'The requested endpoint does not exist'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error':   'Internal Server Error',
        'message': 'An unexpected error occurred'
    }), 500

# ─────────────────────────────────────────────
#  Run
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Wikipedia Data Intelligence API v2.0")
    print("=" * 50)
    print("API running at: http://localhost:5000")
    print("Services: scraping, tree analysis, comparison, patching, and clustering")
    print("=" * 50)

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
