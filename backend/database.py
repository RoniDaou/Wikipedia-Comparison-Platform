"""
MongoDB database handler for country infobox data, comparison artifacts,
similarity matrices, cluster results, and application usage metrics.
"""
import os
from dotenv import load_dotenv

load_dotenv()
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from typing import Dict, List, Optional
from datetime import datetime, timezone
import re
import unicodedata
from collections import OrderedDict
from bson import ObjectId


class WikipediaDatabase:
    """Handles MongoDB operations for Wikipedia infobox data"""

    def __init__(self, connection_string=None):
        if connection_string is None:
            connection_string = os.getenv("MONGO_URI")
            
        self.client = MongoClient(connection_string)
        self.db = self.client['wikipedia_scraper']
        self.countries_collection   = self.db['countries']
        self.comparisons_collection = self.db['comparisons']
        self.editedcountries        = self.db['editedcountries']
        self.comparisons            = self.comparisons_collection  # compatibility alias
        self.similarity_matrix_col  = self.db['similarity_matrix']
        self.cluster_results_col    = self.db['cluster_results']
        self.metrics_collection     = self.db['application_metrics']
        self._create_indexes()

    # ══════════════════════════════════════════════════════════════════════
    #  Indexes
    # ══════════════════════════════════════════════════════════════════════

    def _create_indexes(self):
        try:
            self.countries_collection.drop_index("country_name_1")
        except Exception:
            pass
        self.countries_collection.create_index(
            [("country_name", ASCENDING)],
            unique=True,
            collation={'locale': 'en', 'strength': 2}
        )
        self.countries_collection.create_index([("scraped_at", DESCENDING)])
        self.comparisons_collection.create_index([
            ("country1", ASCENDING),
            ("country2", ASCENDING),
            ("compared_at", DESCENDING)
        ])
        self.similarity_matrix_col.create_index([("saved_at", DESCENDING)])
        self.cluster_results_col.create_index([
            ("algorithm", ASCENDING),
            ("saved_at",  DESCENDING)
        ])
        self.metrics_collection.create_index([("updated_at", DESCENDING)])

    # ══════════════════════════════════════════════════════════════════════
    #  Name normalisation helpers
    # ══════════════════════════════════════════════════════════════════════

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

    def _normalize_country_name(self, country_name: str) -> str:
        name = re.sub(r'\s*\([^)]*\)', '', country_name)
        name = name.replace('_', ' ')
        name = self._normalize_unicode(name)
        name = ' '.join(name.split())
        name = self._normalize_case(name)
        return name.strip()

    # ══════════════════════════════════════════════════════════════════════
    #  Country CRUD
    # ══════════════════════════════════════════════════════════════════════

    def insert_country(self, infobox_data: Dict) -> bool:
        try:
            doc = dict(infobox_data)
            country_name = self._normalize_country_name(doc['country_name'])
            doc['country_name'] = country_name

            if isinstance(doc.get('fields'), dict):
                ordered = OrderedDict(doc['fields'].items())
                doc['fields']       = ordered
                doc['_field_order'] = list(ordered.keys())

            print(f"[DB] Attempting to insert/update: {country_name}")
            existing = self.countries_collection.find_one(
                {'country_name': country_name},
                collation={'locale': 'en', 'strength': 2}
            )
            if existing:
                self.countries_collection.update_one(
                    {'_id': existing['_id']}, {'$set': doc}
                )
                print(f"[DB] ♻️  Updated: {country_name}")
            else:
                self.countries_collection.insert_one(doc)
                print(f"[DB] ✅  Inserted: {country_name}")
            return True
        except Exception as e:
            print(f"[DB] ❌  Error: {e}")
            return False

    def insert_multiple_countries(self, infobox_data_list: List[Dict]) -> int:
        return sum(1 for d in infobox_data_list if self.insert_country(d))

    def get_country(self, country_name: str) -> Optional[Dict]:
        print(f"\n[GET_COUNTRY] Looking for: {country_name}")
        result = self.countries_collection.find_one(
            {'country_name': country_name},
            collation={'locale': 'en', 'strength': 2}
        )
        if not result:
            normalized = self._normalize_country_name(country_name)
            if normalized != country_name:
                result = self.countries_collection.find_one(
                    {'country_name': normalized},
                    collation={'locale': 'en', 'strength': 2}
                )
        if result:
            result['_id'] = str(result['_id'])
            fields = result.get('fields', {})
            if isinstance(fields, dict) and '_field_order' in result:
                ordered = OrderedDict()
                for key in result['_field_order']:
                    if key in fields:
                        ordered[key] = fields[key]
                for key, val in fields.items():
                    if key not in ordered:
                        ordered[key] = val
                result['fields'] = ordered
            print(f"[GET_COUNTRY] ✅  Found: {result.get('country_name')}")
        else:
            print(f"[GET_COUNTRY] ❌  Not found: {country_name}")
        return result

    def get_country_names(self) -> List[str]:
        docs = list(self.countries_collection.find({}, {'country_name': 1}))
        return sorted([d['country_name'] for d in docs if 'country_name' in d])

    def _ensure_usage_metrics(self) -> None:
        """Create the singleton metrics document without resetting existing data."""
        baseline = self.comparisons_collection.count_documents({})
        self.metrics_collection.update_one(
            {'_id': 'usage'},
            {
                '$setOnInsert': {
                    'total_comparisons': baseline,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )

    def record_comparisons(self, count: int = 1) -> int:
        """Atomically add successful comparison operations to the usage total."""
        count = int(count)
        if count <= 0:
            return self.get_comparison_count()

        self._ensure_usage_metrics()
        now = datetime.now(timezone.utc).isoformat()
        metric = self.metrics_collection.find_one_and_update(
            {'_id': 'usage'},
            {
                '$inc': {'total_comparisons': count},
                '$set': {'updated_at': now}
            },
            return_document=ReturnDocument.AFTER
        )
        return int(metric.get('total_comparisons', 0)) if metric else 0

    def get_comparison_count(self) -> int:
        """Return the persistent number of successful comparison operations."""
        self._ensure_usage_metrics()
        metric = self.metrics_collection.find_one({'_id': 'usage'}) or {}
        return int(metric.get('total_comparisons', 0))

    def get_statistics(self) -> Dict:
        total_countries = self.countries_collection.count_documents({})
        latest = self.countries_collection.find_one({}, sort=[('scraped_at', DESCENDING)])
        return {
            'total_countries': total_countries,
            'total_comparisons': self.get_comparison_count(),
            'last_scrape': latest['scraped_at'] if latest else None
        }

    # ══════════════════════════════════════════════════════════════════════
    #  Comparisons and edited trees
    # ══════════════════════════════════════════════════════════════════════

    def comparison_country_name_exists(self, country_name: str) -> bool:
        return self.comparisons_collection.find_one({'country_name': country_name}) is not None

    def save_comparison_with_country_name(self, country_name: str, patched_json: Dict):
        print(f"\n[SAVE_COMPARISON] Saving: {country_name}")
        if 'fields' in patched_json:
            fields = patched_json['fields']
            field_keys = list(fields.keys())
            print(f"[SAVE_COMPARISON] Fields before insert (first 10):")
            for i, key in enumerate(field_keys[:10]):
                print(f"  [{i+1}] {key}")
            print(f"[SAVE_COMPARISON] Total: {len(field_keys)} fields")

        comparison_doc = {
            'country_name': country_name,
            'fields':       patched_json.get('fields', {}),
            'scraped_at':   patched_json.get('scraped_at'),
            'source_url':   patched_json.get('source_url'),
            'saved_at':     datetime.now(timezone.utc).isoformat()
        }
        if 'fields' in comparison_doc:
            comparison_doc['_field_order'] = list(comparison_doc['fields'].keys())
        self.comparisons.insert_one(comparison_doc)
        print(f"[SAVE_COMPARISON] ✅  Inserted")

    def save_edited_country(self, original_country, edited_tree):
        existing = list(self.editedcountries.find(
            {'country_name': {'$regex': f'^{original_country}_\\d+$'}}
        ).sort('_id', -1).limit(1))
        next_num = 1
        if existing:
            try:
                next_num = int(existing[0].get('country_name', '').split('_')[-1]) + 1
            except Exception:
                next_num = 1
        edited_tree['country_name'] = f"{original_country}_{next_num}"
        if isinstance(edited_tree.get('fields'), dict):
            ordered = OrderedDict(edited_tree['fields'].items())
            edited_tree['fields']       = ordered
            edited_tree['_field_order'] = list(ordered.keys())
        self.editedcountries.insert_one(edited_tree)
        return edited_tree['country_name']

    def get_edited_tree(self, tree_name):
        print(f"\n[GET_EDITED] Looking for: {tree_name}")
        result = self.editedcountries.find_one({'country_name': tree_name})
        if not result:
            print(f"[GET_EDITED] ❌  Not found")
            return None
        print(f"[GET_EDITED] ✅  Found: {result.get('country_name')}")
        fields = result.get('fields', {})
        if isinstance(fields, dict) and '_field_order' in result:
            ordered = OrderedDict()
            for key in result['_field_order']:
                if key in fields:
                    ordered[key] = fields[key]
            for key, val in fields.items():
                if key not in ordered:
                    ordered[key] = val
            result['fields'] = ordered
        result['_id'] = str(result['_id'])
        return result

    def get_all_edited_countries(self):
        docs = list(self.editedcountries.find({}, {'country_name': 1}))
        return sorted([d['country_name'] for d in docs if 'country_name' in d])

    def get_all_comparisons(self) -> List[str]:
        docs = list(self.comparisons_collection.find({}, {'country_name': 1}))
        return sorted([d.get('country_name') for d in docs if d.get('country_name')])

    def get_comparison_by_name(self, comparison_name: str) -> Optional[Dict]:
        print(f"\n[GET_COMPARISON] Looking for: {comparison_name}")
        result = self.comparisons_collection.find_one({'country_name': comparison_name})
        if result:
            fields = result.get('fields', {})
            if '_field_order' in result:
                ordered = {}
                for key in result['_field_order']:
                    if key in fields:
                        ordered[key] = fields[key]
                result['fields'] = ordered
            result['_id'] = str(result['_id'])
            print(f"[GET_COMPARISON] ✅  Found")
        else:
            print(f"[GET_COMPARISON] ❌  Not found")
            edited = self.editedcountries.find_one({'country_name': comparison_name})
            if edited:
                print(f"[GET_COMPARISON] ⚠️  Found in editedcountries instead")
        return result

    @staticmethod
    def convert_fields_to_ordered_array(fields_dict):
        return [{"key": k, "value": v} for k, v in fields_dict.items()]

    @staticmethod
    def convert_ordered_array_to_fields(fields_array):
        if isinstance(fields_array, list):
            return {item["key"]: item["value"] for item in fields_array}
        return fields_array

    # ══════════════════════════════════════════════════════════════════════
    #  Similarity matrices
    #  Each matrix is a separate MongoDB document with its own _id.
    #  Nothing is ever overwritten — you can have many matrices.
    # ══════════════════════════════════════════════════════════════════════

    def save_similarity_matrix(self, matrix_doc: Dict, name: str = '') -> str:
        """
        Insert a NEW similarity matrix (never overwrites existing ones).

        Args:
            matrix_doc : {countries, matrix, count, built_at}
            name       : optional human-readable label

        Returns:
            String _id of the inserted document.
        """
        doc = dict(matrix_doc)
        doc.pop('_id', None)  # never carry over an old _id
        n           = doc.get('count', len(doc.get('countries', [])))
        doc['name'] = name.strip() if name.strip() else \
                      f"Matrix — {n} countries"
        doc['saved_at'] = datetime.now(timezone.utc).isoformat()
        result = self.similarity_matrix_col.insert_one(doc)
        inserted_id = str(result.inserted_id)
        print(f"[DB] ✅  Similarity matrix saved: '{doc['name']}' id={inserted_id}")
        return inserted_id

    def get_similarity_matrix(self, matrix_id: str) -> Optional[Dict]:
        """Retrieve the full matrix document by its string _id."""
        try:
            doc = self.similarity_matrix_col.find_one({'_id': ObjectId(matrix_id)})
        except Exception:
            return None
        if doc:
            doc['_id'] = str(doc['_id'])
        return doc

    def list_similarity_matrices(self) -> List[Dict]:
        """
        List all stored matrices — metadata only (no 'matrix' payload).
        Returns newest first.
        Each item: {_id, name, count, countries, built_at, saved_at}
        """
        docs = list(self.similarity_matrix_col.find(
            {}, {'matrix': 0}
        ).sort('saved_at', DESCENDING))
        for d in docs:
            d['_id'] = str(d['_id'])
        return docs

    def delete_similarity_matrix(self, matrix_id: str) -> bool:
        """Delete one matrix by its string _id. Returns True if deleted."""
        try:
            res = self.similarity_matrix_col.delete_one({'_id': ObjectId(matrix_id)})
            deleted = res.deleted_count > 0
            if deleted:
                print(f"[DB] 🗑  Matrix {matrix_id} deleted")
            return deleted
        except Exception as e:
            print(f"[DB] ❌  delete_similarity_matrix error: {e}")
            return False

    def get_latest_similarity_matrix(self) -> Optional[Dict]:
        """Convenience: full document of the most recently saved matrix."""
        doc = self.similarity_matrix_col.find_one(
            {}, sort=[('saved_at', DESCENDING)]
        )
        if doc:
            doc['_id'] = str(doc['_id'])
        return doc

    # ══════════════════════════════════════════════════════════════════════
    #  Cluster results
    #  Each run is a separate document. Nothing is overwritten.
    # ══════════════════════════════════════════════════════════════════════

    def save_cluster_result(self, result: Dict, name: str = '',
                            matrix_id: str = '') -> str:
        """
        Insert a NEW cluster result (never overwrites existing ones).

        Args:
            result    : full clustering output dict
            name      : optional human-readable label
            matrix_id : string _id of the matrix used (for traceability)

        Returns:
            String _id of the inserted document.
        """
        doc = dict(result)
        doc.pop('_id', None)
        algo = doc.get('algorithm', 'unknown')
        k    = doc.get('k', doc.get('n_clusters', '?'))
        n    = doc.get('n_countries', '?')
        doc['name']      = name.strip() if name.strip() else \
                           f"{algo.upper()} — k={k} — {n} countries"
        doc['matrix_id'] = matrix_id
        doc['saved_at']  = datetime.now(timezone.utc).isoformat()
        res = self.cluster_results_col.insert_one(doc)
        inserted_id = str(res.inserted_id)
        print(f"[DB] ✅  Cluster result saved: '{doc['name']}' id={inserted_id}")
        return inserted_id

    def get_cluster_result(self, result_id: str) -> Optional[Dict]:
        """Retrieve one cluster result by its string _id."""
        try:
            doc = self.cluster_results_col.find_one({'_id': ObjectId(result_id)})
        except Exception:
            return None
        if doc:
            doc['_id'] = str(doc['_id'])
        return doc

    def list_cluster_results(self, algorithm: str = '') -> List[Dict]:
        """
        List all stored cluster results — metadata only (no clusters/labels payload).
        Optionally filter by algorithm. Returns newest first.
        Each item: {_id, name, algorithm, k/n_clusters, n_countries,
                    silhouette, matrix_id, computed_at, saved_at}
        """
        filt = {'algorithm': algorithm} if algorithm else {}
        docs = list(self.cluster_results_col.find(
            filt,
            {'clusters': 0, 'labels': 0}
        ).sort('saved_at', DESCENDING))
        for d in docs:
            d['_id'] = str(d['_id'])
        return docs

    def delete_cluster_result(self, result_id: str) -> bool:
        """Delete one cluster result by its string _id."""
        try:
            res = self.cluster_results_col.delete_one({'_id': ObjectId(result_id)})
            deleted = res.deleted_count > 0
            if deleted:
                print(f"[DB] 🗑  Cluster result {result_id} deleted")
            return deleted
        except Exception as e:
            print(f"[DB] ❌  delete_cluster_result error: {e}")
            return False

    def get_latest_cluster_result(self, algorithm: str = '') -> Optional[Dict]:
        """Convenience: full document of the most recent result (optional algo filter)."""
        filt = {'algorithm': algorithm} if algorithm else {}
        doc  = self.cluster_results_col.find_one(filt, sort=[('saved_at', DESCENDING)])
        if doc:
            doc['_id'] = str(doc['_id'])
        return doc

    # ══════════════════════════════════════════════════════════════════════
    #  Teardown
    # ══════════════════════════════════════════════════════════════════════

    def close(self):
        self.client.close()