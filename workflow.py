#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import threading
import boto3
import json
import re
import random
import numpy as np
from datetime import datetime

app = Flask(__name__)
CORS(app)

jobs = {}
preprocess_jobs = {}
train_jobs = {}
cluster_jobs = {}
persona_jobs = {}
embed_jobs = {}
meta_model = None

S3_BUCKET = 'x'
S3_REGION = 'x'
NAVER_CLIENT_ID = 'x'
NAVER_CLIENT_SECRET = 'x'
CLAUDE_API_KEY = 'x'
PINECONE_API_KEY = 'x'
VOYAGE_API_KEY = 'x'


s3 = boto3.client('s3', region_name=S3_REGION)

def clean_text(t):
    if not t: return ''
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'&amp;', '&', t)
    t = re.sub(r'&lt;', '<', t)
    t = re.sub(r'&gt;', '>', t)
    return t.strip()

def search_naver_cafe(query, display=100, start=1):
    import requests
    url = 'https://openapi.naver.com/v1/search/cafearticle.json'
    headers = {'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET}
    params = {'query': query, 'display': display, 'start': start, 'sort': 'date'}
    try:
        return requests.get(url, headers=headers, params=params, timeout=10).json()
    except:
        return None

def load_data(prefix):
    all_data = []
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        for f in resp.get('Contents', []):
            for line in s3.get_object(Bucket=S3_BUCKET, Key=f['Key'])['Body'].read().decode('utf-8').strip().split('\n'):
                if line:
                    try: all_data.append(json.loads(line))
                    except: pass
    except: pass
    return all_data

def get_embeddings(texts):
    """Voyage AI multilingual embeddings for Korean"""
    import voyageai
    if len(texts) == 0:
        return []
    vo = voyageai.Client(api_key=VOYAGE_API_KEY)
    all_embs = []
    # Batch by 128 (Voyage limit)
    for i in range(0, len(texts), 128):
        batch = texts[i:i+128]
        # Truncate long texts
        batch = [t[:2000] if len(t) > 2000 else t for t in batch]
        batch = [t if t.strip() else '빈 문서' for t in batch]
        try:
            result = vo.embed(batch, model="voyage-multilingual-2")
            all_embs.extend(result.embeddings)
        except Exception as e:
            print(f"Voyage embed error: {e}")
            # Fallback: zero vectors
            all_embs.extend([[0.0]*1024 for _ in batch])
    return all_embs

def search_similar(sid, query, top_k=10):
    """Mini-RAG: Voyage embedding + Pinecone search"""
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
    except:
        return []
    try:
        index_name = f"cx-{sid.replace('_','-').lower()}"[:45]
        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            return []
        index = pc.Index(index_name)
        query_emb = get_embeddings([query])[0]
        results = index.query(vector=query_emb, top_k=top_k, include_metadata=True)
        return [{'score': m.score, **m.metadata} for m in results.matches]
    except Exception as e:
        print(f"Search error: {e}")
        return []

def crawl_keywords(config):
    import time
    from datetime import datetime as dt
    sid, bk, keywords, target = config.get('sid','s0'), config.get('bk',''), config.get('keywords',[]), config.get('target',50000)
    ad_filter = config.get('adFilter',[])
    cafes_filter = config.get('cafes',[])
    exclude_cafes = config.get('excludeCafes',[])
    # Fix: convert strings to lists
    if isinstance(ad_filter, str): ad_filter = [x.strip() for x in ad_filter.split(',') if x.strip()] if ad_filter else []
    if isinstance(cafes_filter, str): cafes_filter = [x.strip() for x in cafes_filter.split(',') if x.strip()] if cafes_filter else []
    if isinstance(exclude_cafes, str): exclude_cafes = [x.strip() for x in exclude_cafes.split(',') if x.strip()] if exclude_cafes else []
    date_from, date_to = config.get('dateFrom',''), config.get('dateTo','')
    results, total = [], 0
    default_exclude = ['중고나라','번개장터','당근','세컨웨어','헬로마켓','중고','장터','부동산','판매','팝니다','삽니다','택배','무료배송','할인코드','쿠폰','홍보','광고','업체','시공','인테리어업체','이사','용달','대출','보험설계사','설계사모집','모집']
    all_exclude = list(set(default_exclude + exclude_cafes))
    date_from_dt, date_to_dt = None, None
    if date_from:
        try: date_from_dt = dt.strptime(date_from, '%Y-%m-%d')
        except: pass
    if date_to:
        try: date_to_dt = dt.strptime(date_to, '%Y-%m-%d')
        except: pass
    for kw in keywords:
        if total >= target: break
        query = f"{bk} {kw}"
        for start in range(1, 1001, 100):
            if total >= target: break
            data = search_naver_cafe(query, 100, start)
            if not data or 'items' not in data: break
            for item in data.get('items', []):
                if total >= target: break
                title, desc, link, cafe = clean_text(item.get('title','')), clean_text(item.get('description','')), item.get('link',''), item.get('cafename','')
                postdate = item.get('postdate', '')
                if postdate and (date_from_dt or date_to_dt):
                    try:
                        post_dt = dt.strptime(postdate, '%Y%m%d')
                        if date_from_dt and post_dt < date_from_dt: continue
                        if date_to_dt and post_dt > date_to_dt: continue
                    except: pass
                combined, cafe_lower = (title + ' ' + desc).lower(), cafe.lower()
                if any(ad.lower() in combined for ad in ad_filter): continue
                if any(ex.lower() in cafe_lower for ex in all_exclude): continue
                if cafes_filter and not any(c.lower() in cafe_lower for c in cafes_filter): continue
                # Quality filter: title or desc must contain the main keyword (bk)
                if bk.lower() not in (title + ' ' + desc).lower():
                    continue
                results.append({'kw': kw, 'title': title, 'desc': desc, 'link': link, 'cafe': cafe, 'date': postdate})
                total += 1
                jobs[sid]['total'] = total
            if len(results) >= 500:
                ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                s3.put_object(Bucket=S3_BUCKET, Key=f"crawl/{sid}/{ts}.jsonl", Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in results).encode('utf-8'))
                results = []
            time.sleep(0.1)
    if results:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        s3.put_object(Bucket=S3_BUCKET, Key=f"crawl/{sid}/{ts}.jsonl", Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in results).encode('utf-8'))
    return total

def preprocess_data(config):
    sid, ad_filter = config.get('sid','s0'), config.get('adFilter',[])
    exclude_cafes = config.get('excludeCafes', [])
    if isinstance(exclude_cafes, str):
        exclude_cafes = [x.strip() for x in exclude_cafes.split(',') if x.strip()]
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"crawl/{sid}/")
        all_data, seen = [], set()
        for f in resp.get('Contents', []):
            for line in s3.get_object(Bucket=S3_BUCKET, Key=f['Key'])['Body'].read().decode('utf-8').strip().split('\n'):
                if line:
                    try: all_data.append(json.loads(line))
                    except: pass
        original = len(all_data)
        filtered = []
        for idx, item in enumerate(all_data):
            title, desc, link = item.get('title',''), item.get('desc',''), item.get('link','')
            if any(ad.lower() in (title+' '+desc).lower() for ad in ad_filter): continue
            cafe = item.get('cafe','').lower()
            if exclude_cafes and any(ex.lower() in cafe for ex in exclude_cafes): continue
            if link in seen: continue
            seen.add(link)
            item['idx'] = idx
            if len(title) < 5 and len(desc) < 10: continue
            filtered.append(item)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        s3.put_object(Bucket=S3_BUCKET, Key=f"preprocessed/{sid}/{ts}.jsonl", Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in filtered).encode('utf-8'))
        preprocess_jobs[sid] = {'status': 'done', 'original': original, 'filtered': len(filtered)}
    except Exception as e:
        preprocess_jobs[sid] = {'status': 'error', 'error': str(e)}

def get_llm_predictions(batch, bk, problem_def):
    import requests
    try:
        prompt = f'제품: "{bk}"\n문제정의: {problem_def}\n\n아래 글들이 해당 제품 관련인지 판단. 1(관련) 또는 0(무관)으로만.\n\n'
        for j, item in enumerate(batch):
            prompt += f"{j+1}. {item.get('title','')} - {item.get('desc','')[:100]}\n"
        prompt += "\n답변: 1,0,1,0,..."
        resp = requests.post('https://api.anthropic.com/v1/messages', headers={'x-api-key': CLAUDE_API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'}, json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 1000, 'messages': [{'role': 'user', 'content': prompt}]}, timeout=60)
        if resp.status_code == 200:
            nums = re.findall(r'[01]', resp.json()['content'][0]['text'])
            preds = [int(n) for n in nums[:len(batch)]]
            while len(preds) < len(batch): preds.append(0)
            return preds
    except: pass
    return [0] * len(batch)

def train_models(config):
    """3중 준지도 학습: LSTM + CNN + GRU + LLM 앙상블"""
    sid = config.get('sid', 's0')
    train_jobs[sid] = {'status': 'running', 'phase': 'init', 'progress': 0}
    
    try:
        # Load labeled data from session
        labeled = []
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=f"sessions/{sid}/session.json")
            session = json.loads(obj['Body'].read().decode('utf-8'))
            labeled = session.get('labeledData', [])
        except:
            pass
        
        if len(labeled) < 5:
            train_jobs[sid] = {'status': 'error', 'error': 'Need at least 5 labeled samples'}
            return
        
        texts = [f"{d.get('title','')} {d.get('desc','')}" for d in labeled]
        labels = [1 if d.get('label') == 'relevant' or d.get('label') == 1 else 0 for d in labeled]
        
        train_jobs[sid]['progress'] = 10
        train_jobs[sid]['phase'] = 'preparing'
        
        # Try tensorflow first, fallback to sklearn
        use_tf = False
        try:
            import tensorflow as tf
            from tensorflow.keras.preprocessing.text import Tokenizer
            from tensorflow.keras.preprocessing.sequence import pad_sequences
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Embedding, LSTM, GRU, Conv1D, GlobalMaxPooling1D, Dense, Dropout
            use_tf = True
        except ImportError:
            pass
        
        if use_tf:
            # ===== TensorFlow: LSTM + CNN + GRU =====
            import numpy as np
            MAX_WORDS = 10000
            MAX_LEN = 200
            
            tokenizer = Tokenizer(num_words=MAX_WORDS, oov_token='<OOV>')
            tokenizer.fit_on_texts(texts)
            sequences = tokenizer.texts_to_sequences(texts)
            X = pad_sequences(sequences, maxlen=MAX_LEN, padding='post', truncating='post')
            y = np.array(labels)
            
            train_jobs[sid]['progress'] = 20
            train_jobs[sid]['phase'] = 'LSTM'
            
            # Model 1: LSTM
            m1 = Sequential([
                Embedding(MAX_WORDS, 128, input_length=MAX_LEN),
                LSTM(64, dropout=0.2, recurrent_dropout=0.2),
                Dense(32, activation='relu'),
                Dropout(0.5),
                Dense(1, activation='sigmoid')
            ])
            m1.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
            m1.fit(X, y, epochs=5, batch_size=32, verbose=0)
            s1 = m1.evaluate(X, y, verbose=0)[1]
            
            train_jobs[sid]['progress'] = 40
            train_jobs[sid]['phase'] = 'CNN'
            
            # Model 2: CNN
            m2 = Sequential([
                Embedding(MAX_WORDS, 128, input_length=MAX_LEN),
                Conv1D(64, 5, activation='relu'),
                GlobalMaxPooling1D(),
                Dense(32, activation='relu'),
                Dropout(0.5),
                Dense(1, activation='sigmoid')
            ])
            m2.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
            m2.fit(X, y, epochs=5, batch_size=32, verbose=0)
            s2 = m2.evaluate(X, y, verbose=0)[1]
            
            train_jobs[sid]['progress'] = 60
            train_jobs[sid]['phase'] = 'GRU'
            
            # Model 3: GRU
            m3 = Sequential([
                Embedding(MAX_WORDS, 128, input_length=MAX_LEN),
                GRU(64, dropout=0.2, recurrent_dropout=0.2),
                Dense(32, activation='relu'),
                Dropout(0.5),
                Dense(1, activation='sigmoid')
            ])
            m3.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
            m3.fit(X, y, epochs=5, batch_size=32, verbose=0)
            s3_score = m3.evaluate(X, y, verbose=0)[1]
            
            train_jobs[sid]['progress'] = 80
            train_jobs[sid]['phase'] = 'classifying'
            
            # Classify all preprocessed data
            all_data = load_data(f"preprocessed/{sid}/")
            if all_data:
                all_texts = [f"{d.get('title','')} {d.get('desc','')}" for d in all_data]
                all_seq = tokenizer.texts_to_sequences(all_texts)
                X_all = pad_sequences(all_seq, maxlen=MAX_LEN, padding='post', truncating='post')
                
                p1 = m1.predict(X_all, verbose=0).flatten()
                p2 = m2.predict(X_all, verbose=0).flatten()
                p3 = m3.predict(X_all, verbose=0).flatten()
                ensemble = (p1 + p2 + p3) / 3
                
                relevant, irrelevant = [], []
                for i, item in enumerate(all_data):
                    if ensemble[i] >= 0.5:
                        item['relevance_score'] = float(ensemble[i])
                        relevant.append(item)
                    else:
                        irrelevant.append(item)
                
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                s3.put_object(Bucket=S3_BUCKET, Key=f"classified/{sid}/relevant_{ts}.jsonl",
                    Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in relevant).encode('utf-8'))
                s3.put_object(Bucket=S3_BUCKET, Key=f"classified/{sid}/irrelevant_{ts}.jsonl",
                    Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in irrelevant).encode('utf-8'))
                
                train_jobs[sid] = {
                    'status': 'done', 'progress': 100, 'phase': 'complete',
                    'total': len(all_data), 'relevant': len(relevant), 'irrelevant': len(irrelevant),
                    'scores': {'LSTM': round(s1, 3), 'CNN': round(s2, 3), 'GRU': round(s3_score, 3)},
                    'models': ['LSTM', 'CNN', 'GRU']
                }
            else:
                train_jobs[sid] = {'status': 'error', 'error': 'No preprocessed data'}
        
        else:
            # ===== Fallback: sklearn =====
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
            from sklearn.model_selection import cross_val_score
            import numpy as np
            
            vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
            X = vec.fit_transform(texts)
            y = np.array(labels)
            
            train_jobs[sid]['progress'] = 20
            train_jobs[sid]['phase'] = 'LogisticRegression'
            
            m1 = LogisticRegression(max_iter=500, C=1.0)
            s1 = cross_val_score(m1, X, y, cv=min(3, len(y)), scoring='accuracy').mean()
            m1.fit(X, y)
            
            train_jobs[sid]['progress'] = 40
            train_jobs[sid]['phase'] = 'RandomForest'
            
            m2 = RandomForestClassifier(n_estimators=100, random_state=42)
            s2 = cross_val_score(m2, X, y, cv=min(3, len(y)), scoring='accuracy').mean()
            m2.fit(X, y)
            
            train_jobs[sid]['progress'] = 60
            train_jobs[sid]['phase'] = 'GradientBoosting'
            
            m3 = GradientBoostingClassifier(n_estimators=100, random_state=42)
            s3_score = cross_val_score(m3, X, y, cv=min(3, len(y)), scoring='accuracy').mean()
            m3.fit(X, y)
            
            train_jobs[sid]['progress'] = 80
            train_jobs[sid]['phase'] = 'classifying'
            
            all_data = load_data(f"preprocessed/{sid}/")
            if all_data:
                all_texts = [f"{d.get('title','')} {d.get('desc','')}" for d in all_data]
                X_all = vec.transform(all_texts)
                p1 = m1.predict_proba(X_all)[:, 1]
                p2 = m2.predict_proba(X_all)[:, 1]
                p3 = m3.predict_proba(X_all)[:, 1]
                ensemble = (p1 + p2 + p3) / 3
                
                relevant, irrelevant = [], []
                for i, item in enumerate(all_data):
                    if ensemble[i] >= 0.5:
                        item['relevance_score'] = float(ensemble[i])
                        relevant.append(item)
                    else:
                        irrelevant.append(item)
                
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                s3.put_object(Bucket=S3_BUCKET, Key=f"classified/{sid}/relevant_{ts}.jsonl",
                    Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in relevant).encode('utf-8'))
                s3.put_object(Bucket=S3_BUCKET, Key=f"classified/{sid}/irrelevant_{ts}.jsonl",
                    Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in irrelevant).encode('utf-8'))
                
                train_jobs[sid] = {
                    'status': 'done', 'progress': 100, 'phase': 'complete (sklearn fallback)',
                    'total': len(all_data), 'relevant': len(relevant), 'irrelevant': len(irrelevant),
                    'scores': {'LR': round(s1, 3), 'RF': round(s2, 3), 'GB': round(s3_score, 3)},
                    'models': ['LogisticRegression', 'RandomForest', 'GradientBoosting']
                }
            else:
                train_jobs[sid] = {'status': 'error', 'error': 'No preprocessed data'}
    
    except Exception as e:
        train_jobs[sid] = {'status': 'error', 'error': str(e)}


def run_clustering(config):
    """Mini-RAG clustering: Voyage embeddings + KMeans"""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    import numpy as np
    sid, num_clusters = config.get('sid','s0'), config.get('num_clusters',0)
    cluster_jobs[sid] = {'status': 'running', 'phase': 'loading', 'progress': 0}
    try:
        data = load_data(f"classified/{sid}/relevant_")
        if not data:
            data = load_data(f"preprocessed/{sid}/")
        if not data:
            cluster_jobs[sid] = {'status': 'error', 'error': 'no data'}
            return
        cluster_jobs[sid]['progress'] = 10
        cluster_jobs[sid]['phase'] = 'embedding'
        
        # Voyage AI embeddings
        texts = [f"{d.get('title','')} {d.get('desc','')}" for d in data]
        embeddings = get_embeddings(texts)
        X = np.array(embeddings)
        
        cluster_jobs[sid]['progress'] = 40
        cluster_jobs[sid]['phase'] = 'clustering'
        
        # Auto-determine k
        if num_clusters == 0:
            best_k, best_score = 5, -1
            for k in range(3, min(15, len(data)//10+1)):
                try:
                    km = KMeans(n_clusters=k, random_state=42, n_init=10)
                    labels = km.fit_predict(X)
                    score = silhouette_score(X, labels)
                    if score > best_score:
                        best_k, best_score = k, score
                except:
                    pass
            num_clusters = best_k
        
        cluster_jobs[sid]['progress'] = 60
        kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)
        
        cluster_jobs[sid]['progress'] = 80
        
        # Build cluster info with top keywords
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(max_features=3000, ngram_range=(1,2), min_df=2, max_df=0.95)
        try:
            tfidf = vec.fit_transform(texts)
            fnames = list(vec.get_feature_names_out())
        except:
            fnames = []
        
        clusters = {}
        for i in range(num_clusters):
            idxs = [j for j, l in enumerate(labels) if l == i]
            if idxs and fnames:
                tfidf_mean = tfidf[idxs].mean(axis=0).A1
                top_kw = [fnames[x] for x in tfidf_mean.argsort()[-10:][::-1]]
            else:
                top_kw = []
            # Sample docs for Mini-RAG evidence
            samples = []
            for j in idxs[:3]:
                samples.append({'title': data[j].get('title','')[:80], 'desc': data[j].get('desc','')[:150], 'cafe': data[j].get('cafe',''), 'kw': data[j].get('kw','')})
            clusters[str(i)] = {'id': i, 'size': len(idxs), 'keywords': top_kw, 'name': ' / '.join(top_kw[:3]), 'samples': samples}
        
        for i, item in enumerate(data):
            item['cluster'] = int(labels[i])
        
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        for cid in range(num_clusters):
            cdata = [d for d in data if d.get('cluster') == cid]
            s3.put_object(Bucket=S3_BUCKET, Key=f"clusters/{sid}/cluster_{cid}_{ts}.jsonl",
                Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in cdata).encode('utf-8'))
        
        cluster_jobs[sid] = {'status': 'done', 'progress': 100, 'num_clusters': num_clusters, 'total': len(data), 'clusters': clusters}
    except Exception as e:
        cluster_jobs[sid] = {'status': 'error', 'error': str(e)}

def run_embedding(config):
    """Mini-RAG: Voyage embeddings -> Pinecone storage"""
    sid = config.get('sid', 's0')
    embed_jobs[sid] = {'status': 'running', 'progress': 0, 'phase': 'loading'}
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Load data
        data = load_data(f"classified/{sid}/relevant_")
        if not data:
            data = load_data(f"preprocessed/{sid}/")
        if not data:
            embed_jobs[sid] = {'status': 'error', 'error': 'no data'}
            return
        
        embed_jobs[sid]['progress'] = 10
        embed_jobs[sid]['phase'] = 'embedding'
        
        # Create/get index
        index_name = f"cx-{sid.replace('_','-').lower()}"[:45]
        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            pc.create_index(name=index_name, dimension=1024, metric='cosine',
                spec={"serverless": {"cloud": "aws", "region": "us-east-1"}})
        index = pc.Index(index_name)
        
        embed_jobs[sid]['progress'] = 20
        
        # Embed and upsert in batches
        batch_size = 50
        for i in range(0, len(data), batch_size):
            batch = data[i:i+batch_size]
            texts = [f"{d.get('title','')} {d.get('desc','')}" for d in batch]
            embeddings = get_embeddings(texts)
            
            vectors = []
            for j, (d, emb) in enumerate(zip(batch, embeddings)):
                # Skip zero vectors (empty text fallback)
                if any(v != 0.0 for v in emb):
                    vectors.append({
                        'id': f"doc_{i+j}",
                        'values': emb,
                        'metadata': {
                            'title': d.get('title','')[:200],
                            'desc': d.get('desc','')[:500],
                            'kw': d.get('kw',''),
                            'cafe': d.get('cafe',''),
                            'cluster': d.get('cluster', -1)
                        }
                    })
            if vectors:
                index.upsert(vectors=vectors)
            embed_jobs[sid]['progress'] = 20 + int(70 * (i+len(batch)) / len(data))
        
        embed_jobs[sid] = {'status': 'done', 'progress': 100, 'total': len(data), 'index': index_name}
    except Exception as e:
        embed_jobs[sid] = {'status': 'error', 'error': str(e)}

def run_persona(config):
    import requests
    sid, bk = config.get('sid','s0'), config.get('bk','')
    persona_jobs[sid] = {'status': 'running', 'progress': 0}
    try:
        all_data = load_data(f"clusters_refined/{sid}/data_")
        if not all_data:
            all_data = load_data(f"clusters/{sid}/cluster_")
        if not all_data:
            persona_jobs[sid] = {'status': 'error', 'error': 'no data'}
            return
        clusters = {}
        for item in all_data:
            cid = item.get('cluster', 0)
            if cid not in clusters: clusters[cid] = []
            clusters[cid].append(item)
        persona_jobs[sid]['progress'] = 20
        # Load past good naming examples for learning
        past_examples = ""
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key="naming_examples/good_names.json")
            examples = json.loads(obj['Body'].read().decode('utf-8'))
            if examples:
                past_examples = "\n## 과거 좋은 네이밍 사례 (참고용, 그대로 복사 금지!)\n"
                for ex in examples[-10:]:
                    past_examples += f"- 산업:{ex.get('industry','')}, 클러스터:{ex.get('cluster','')}, 페르소나:{', '.join(ex.get('personas',[]))}\n"
        except:
            pass
        all_cluster_text = ""
        for cid in sorted(clusters.keys()):
            # Mini-RAG: retrieve representative docs from Pinecone
            items = clusters[cid][:20]
            try:
                rag_docs = search_similar(sid, ' '.join([x.get('kw','') for x in clusters[cid][:5]]), top_k=10)
                if rag_docs:
                    items = [{'title': d.get('title',''), 'desc': d.get('desc','')} for d in rag_docs]
            except:
                pass
            text = "\n".join([f"- {x.get('title','')} | {x.get('desc','')[:100]}" for x in items])
            # Count unique keywords for diversity
            kw_set = set([x.get('kw','') for x in clusters[cid] if x.get('kw','')])
            all_cluster_text += f"\n### 클러스터 {cid+1} ({len(clusters[cid])}건, 키워드다양성: {len(kw_set)}개)\n{text}\n" 
        prompt = f"""제품군: "{bk}"

아래는 소비자 데이터를 클러스터링한 결과입니다:
{all_cluster_text}

## 임무
{past_examples}
각 클러스터에 이름을 붙이고, 각 클러스터의 데이터 크기와 다양성에 따라 페르소나를 도출해주세요.

## 페르소나 수 결정 기준 (SNA 기반)
- 데이터 50건 미만: 페르소나 1개
- 데이터 50~200건: 페르소나 2개
- 데이터 200건 이상: 페르소나 3개
- 클러스터 내 키워드 다양성이 높으면 +1개 추가 가능
- 전체 페르소나 수는 클러스터 수의 1.5~2배가 적정

## 네이밍 규칙
- 제품명 직접 언급 금지
- 상황/행동/심리를 위트있고 은유적으로 표현

## 출력 형식 (JSON)
[
  {{
    "cluster_id": 1,
    "cluster_name": "클러스터명",
    "personas": [
      {{
        "name": "페르소나명",
        "situation": "상황",
        "pain_point": "핵심 고민",
        "insight": "마케팅 인사이트"
      }}
    ]
  }}
]

JSON만 출력:"""
        resp = requests.post('https://api.anthropic.com/v1/messages', headers={'x-api-key': CLAUDE_API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'}, json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 8000, 'messages': [{'role': 'user', 'content': prompt}]}, timeout=180)
        persona_jobs[sid]['progress'] = 80
        personas = []
        if resp.status_code == 200:
            match = re.search(r'\[[\s\S]*\]', resp.json()['content'][0]['text'])
            if match:
                personas = json.loads(match.group())
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        result = {'bk': bk, 'personas': personas, 'num_clusters': len(clusters), 'total_docs': len(all_data), 'timestamp': ts}
        s3.put_object(Bucket=S3_BUCKET, Key=f"personas/{sid}/result_{ts}.json", Body=json.dumps(result, ensure_ascii=False).encode('utf-8'))
        persona_jobs[sid] = {'status': 'done', 'progress': 100, 'personas': personas, 'num_clusters': len(clusters), 'total_docs': len(all_data)}
    except Exception as e:
        persona_jobs[sid] = {'status': 'error', 'error': str(e)}

# ============ API Routes ============

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/crawl', methods=['POST'])
def start_crawl():
    config = request.json
    sid = config.get('sid', 's_unknown')
    jobs[sid] = {'status': 'running', 'total': 0}
    threading.Thread(target=lambda: jobs.update({sid: {'status': 'done', 'total': crawl_keywords(config)}}), daemon=True).start()
    return jsonify({'sid': sid, 'status': 'started'})

@app.route('/status/<sid>')
def get_status(sid):
    job = jobs.get(sid, {})
    status = job.get('status', 'not_found')
    total = job.get('total', 0)
    cafe_stats = []
    # If not in memory, check S3 for existing crawl data
    if status == 'not_found':
        try:
            existing = load_data(f"crawl/{sid}/")
            if existing:
                status = 'done'
                total = len(existing)
                jobs[sid] = {'status': 'done', 'total': total}
        except:
            pass
    if status == 'done':
        try:
            all_data = load_data(f"crawl/{sid}/")
            cafe_count = {}
            for d in all_data:
                cafe = d.get('cafe', '기타')
                cafe_count[cafe] = cafe_count.get(cafe, 0) + 1
            cafe_stats = sorted([{'cafe': k, 'count': v} for k, v in cafe_count.items()], key=lambda x: -x['count'])
        except:
            pass
    return jsonify({'status': status, 'total': total, 'cafe_stats': cafe_stats})

@app.route('/preprocess', methods=['POST'])
def start_preprocess():
    config = request.json
    sid = config.get('sid', 's_unknown')
    preprocess_jobs[sid] = {'status': 'running'}
    threading.Thread(target=lambda: preprocess_data(config), daemon=True).start()
    return jsonify({'sid': sid, 'status': 'started'})

@app.route('/preprocess-status/<sid>')
def get_preprocess_status(sid):
    return jsonify(preprocess_jobs.get(sid, {'status': 'not_found'}))

@app.route('/train', methods=['POST'])
def start_train():
    config = request.json
    sid = config.get('sid', 's_unknown')
    train_jobs[sid] = {'status': 'running', 'phase': 'init', 'progress': 0}
    threading.Thread(target=lambda: train_models(config), daemon=True).start()
    return jsonify({'sid': sid, 'status': 'started'})

@app.route('/train-status/<sid>')
def get_train_status(sid):
    return jsonify(train_jobs.get(sid, {'status': 'not_found'}))

@app.route('/cluster', methods=['POST'])
def start_cluster():
    config = request.json
    sid = config.get('sid', 's_unknown')
    cluster_jobs[sid] = {'status': 'running', 'phase': 'init', 'progress': 0}
    threading.Thread(target=lambda: run_clustering(config), daemon=True).start()
    return jsonify({'sid': sid, 'status': 'started'})

@app.route('/cluster-status/<sid>')
def get_cluster_status(sid):
    job = cluster_jobs.get(sid)
    if job and job.get('status') in ('running', 'done', 'error'):
        return jsonify(job)
    # Fallback: check S3
    try:
        cd = load_data(f"clusters_refined/{sid}/data_")
        if not cd: cd = load_data(f"clusters/{sid}/cluster_")
        if cd:
            cl = {}
            for it in cd:
                c = it.get('cluster', 0)
                if c not in cl: cl[c] = []
                cl[c].append(it)
            clusters = {}
            for c in sorted(cl.keys()):
                items = cl[c]
                # Top keywords by frequency
                word_count = {}
                for it in items:
                    kw = it.get('kw', '')
                    if kw:
                        word_count[kw] = word_count.get(kw, 0) + 1
                top_kw = sorted(word_count.items(), key=lambda x: -x[1])[:8]
                # Sample docs (2-3)
                samples = []
                for it in items[:3]:
                    samples.append({'title': it.get('title','')[:80], 'desc': it.get('desc','')[:150], 'cafe': it.get('cafe',''), 'kw': it.get('kw','')})
                clusters[str(c)] = {'size': len(items), 'keywords': [k[0] for k in top_kw], 'keyword_counts': {k[0]:k[1] for k in top_kw}, 'samples': samples}
            return jsonify({'status': 'done', 'num_clusters': len(cl), 'clusters': clusters})
    except:
        pass
    return jsonify({'status': 'not_found'})

@app.route('/cluster-refine', methods=['POST'])
def cluster_refine():
    import requests
    from sklearn.feature_extraction.text import TfidfVectorizer
    config = request.json
    sid, keep, merge = config.get('sid','s_unknown'), config.get('keepClusters',[]), config.get('mergeClusters',[])
    bk = config.get('bk', '')
    try:
        all_data = load_data(f"clusters/{sid}/cluster_")
        if keep:
            all_data = [d for d in all_data if d.get('cluster') in set(keep)]
        if merge and len(merge) > 1:
            for item in all_data:
                if item.get('cluster') in set(merge):
                    item['cluster'] = merge[0]
        unique = sorted(set(d.get('cluster',-1) for d in all_data))
        cmap = {old: new for new, old in enumerate(unique)}
        for item in all_data:
            item['cluster'] = cmap.get(item.get('cluster',-1), 0)
        texts = [f"{d.get('title','')} {d.get('desc','')}" for d in all_data]
        vec = TfidfVectorizer(max_features=3000, ngram_range=(1,2), min_df=2, max_df=0.95)
        X = vec.fit_transform(texts)
        fnames = list(vec.get_feature_names_out())
        clusters_info = {}
        for cid in range(len(unique)):
            idxs = [j for j, d in enumerate(all_data) if d.get('cluster') == cid]
            cdata = [all_data[j] for j in idxs]
            if idxs:
                tfidf_mean = X[idxs].mean(axis=0).A1
                top_kw = [fnames[x] for x in tfidf_mean.argsort()[-10:][::-1]]
            else:
                top_kw = []
            samples = [{'title': d.get('title','')[:80], 'desc': d.get('desc','')[:150], 'cafe': d.get('cafe','')} for d in cdata[:5]]
            clusters_info[str(cid)] = {'id': cid, 'size': len(cdata), 'keywords': top_kw, 'samples': samples, 'name': ''}
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        s3.put_object(Bucket=S3_BUCKET, Key=f"clusters_refined/{sid}/data_{ts}.jsonl", Body='\n'.join(json.dumps(r, ensure_ascii=False) for r in all_data).encode('utf-8'))
        return jsonify({'status': 'done', 'kept_clusters': len(unique), 'total_docs': len(all_data), 'clusters': clusters_info})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/embed', methods=['POST'])
def start_embed():
    config = request.json
    sid = config.get('sid', 's_unknown')
    embed_jobs[sid] = {'status': 'running', 'progress': 0}
    threading.Thread(target=lambda: run_embedding(config), daemon=True).start()
    return jsonify({'sid': sid, 'status': 'started'})

@app.route('/embed-status/<sid>')
def get_embed_status(sid):
    return jsonify(embed_jobs.get(sid, {'status': 'not_found'}))

@app.route('/persona', methods=['POST'])
def start_persona():
    config = request.json
    sid = config.get('sid', 's_unknown')
    persona_jobs[sid] = {'status': 'running', 'progress': 0}
    threading.Thread(target=lambda: run_persona(config), daemon=True).start()
    return jsonify({'sid': sid, 'status': 'started'})

@app.route('/persona-status/<sid>')
def get_persona_status(sid):
    # First check in-memory jobs
    job = persona_jobs.get(sid)
    if job and job.get('status') in ('running', 'done', 'error'):
        return jsonify(job)
    # Fallback: check S3 for saved persona results
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"personas/{sid}/")
        if resp.get('Contents'):
            latest = sorted(resp['Contents'], key=lambda x: x['Key'], reverse=True)[0]
            obj = s3.get_object(Bucket=S3_BUCKET, Key=latest['Key'])
            persona_data = json.loads(obj['Body'].read().decode('utf-8'))
            return jsonify({'status': 'done', 'personas': persona_data.get('personas', [])})
    except:
        pass
    return jsonify({'status': 'not_found'})

@app.route('/save-session', methods=['POST'])
def save_session():
    data = request.json
    sid = data.get('sid', 's_unknown')
    try:
        s3.put_object(Bucket=S3_BUCKET, Key=f"sessions/{sid}/session.json", Body=json.dumps(data.get('data',{}), ensure_ascii=False).encode('utf-8'))
        return jsonify({'status': 'saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/session/<sid>')
def get_session(sid):
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=f"sessions/{sid}/session.json")
        return jsonify({'status': 'ok', 'data': json.loads(obj['Body'].read().decode('utf-8'))})
    except:
        return jsonify({'status': 'not_found', 'data': None})

@app.route('/sessions')
def list_sessions():
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix='sessions/', Delimiter='/')
        sessions = []
        for p in resp.get('CommonPrefixes', []):
            sid = p['Prefix'].replace('sessions/', '').rstrip('/')
            try:
                obj = s3.get_object(Bucket=S3_BUCKET, Key=f"sessions/{sid}/session.json")
                d = json.loads(obj['Body'].read().decode('utf-8'))
                sessions.append({'sid': sid, 'bk': d.get('bk',''), 'step': d.get('step','')})
            except:
                sessions.append({'sid': sid, 'bk': '', 'step': ''})
        return jsonify({'status': 'ok', 'sessions': sorted(sessions, key=lambda x: x['sid'], reverse=True)[:20]})
    except:
        return jsonify({'status': 'error', 'sessions': []})

@app.route('/sample/<sid>')
def get_sample(sid):
    pct = int(request.args.get('percent', 2))
    try:
        all_data = load_data(f"preprocessed/{sid}/")
        total = len(all_data)
        cnt = max(10, int(total * pct / 100))
        samples = random.sample(all_data, min(cnt, len(all_data))) if all_data else []
        return jsonify({'status': 'ok', 'samples': samples[:20], 'total': total})
    except:
        return jsonify({'status': 'error', 'samples': [], 'total': 0})

@app.route('/search', methods=['POST'])
def search_docs():
    config = request.json
    sid, query, top_k = config.get('sid','s0'), config.get('query',''), config.get('top_k',10)
    results = search_similar(sid, query, top_k)
    return jsonify({'status': 'ok', 'results': results})

# ============ Chatbot ============

@app.route('/chat', methods=['POST'])
def chat_agent():
    import requests as req
    try:
        config = request.json or {}
        sid = config.get('sid', 's0')
        query = config.get('query', '')
        pipeline_ctx = config.get('pipeline_context', '')
    
        similar_docs = search_similar(sid, query, top_k=5)
    
        persona_info = ""
        try:
            resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"personas/{sid}/")
            if resp.get('Contents'):
                latest = sorted(resp['Contents'], key=lambda x: x['Key'], reverse=True)[0]
                obj = s3.get_object(Bucket=S3_BUCKET, Key=latest['Key'])
                persona_data = json.loads(obj['Body'].read().decode('utf-8'))
                persona_info = json.dumps(persona_data.get('personas', []), ensure_ascii=False, indent=2)
        except:
            pass
    
        cluster_info = ""
        try:
            cd = load_data(f"clusters_refined/{sid}/data_")
            if not cd: cd = load_data(f"clusters/{sid}/cluster_")
            if cd:
                cl = {}
                for it in cd:
                    c = it.get('cluster',0)
                    if c not in cl: cl[c] = []
                    cl[c].append(it)
                cluster_info = f"총 {len(cl)}개 클러스터, {len(cd)}건\n"
                for c in sorted(cl.keys()):
                    s = ", ".join([x.get('title','')[:30] for x in cl[c][:3]])
                    cluster_info += f"  클러스터{c+1} ({len(cl[c])}건): {s}\n"
        except:
            pass
    
        rag_context = ""
        for doc in similar_docs:
            rag_context += f"- {doc.get('title','')} | {doc.get('desc','')[:200]}\n"
    
        prompt = f"""당신은 DCX 파이프라인 소비자 인사이트 전문가입니다.

## 파이프라인 상태
{pipeline_ctx if pipeline_ctx else "정보 없음"}

## 페르소나 분석 결과
{persona_info if persona_info else "아직 분석 전"}

## 클러스터 정보
{cluster_info if cluster_info else "없음"}

## RAG 검색 결과
{rag_context if rag_context else "없음"}

## 역할
- 파이프라인 각 단계 결과를 분석/평가
- 클러스터/페르소나에 대한 개선 제안
- 마케팅 인사이트와 실행 가능한 전략 제안
- 사용자 피드백을 반영한 조언
- 키워드 추가 요청 처리

## 키워드 추가 기능
사용자가 키워드 추가를 요청하면 (예: "화재 추가해줘") 답변 마지막 줄에 반드시:
ADDED_KEYWORDS: 화재, 침수, 누수
형식으로 작성하세요. 1~2단어 명사형 키워드만. 시스템이 자동으로 추가합니다.

## 질문
{query}

절대로 이모티콘, 이모지, 특수문자(✅🔥💡📊 등)를 사용하지 마세요. 마크다운 기호(**,##,###,- 등)도 사용하지 마세요. 순수 텍스트 문장으로만 답변하세요. 한국어로 답변:"""

        resp = req.post(
            'https://api.anthropic.com/v1/messages',
            headers={'x-api-key': CLAUDE_API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
            json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 2000, 'messages': [{'role': 'user', 'content': prompt}]},
            timeout=60
        )
        if resp.status_code == 200:
            answer = resp.json()['content'][0]['text']
            # Detect keyword additions
            added_kw = []
            import re as re2
            kw_match = re2.search(r'ADDED_KEYWORDS:\s*(.+)', answer)
            if kw_match:
                kw_str = kw_match.group(1).strip()
                added_kw = [k.strip() for k in kw_str.split(',') if k.strip()]
                answer = re2.sub(r'ADDED_KEYWORDS:\s*.+', '', answer).strip()
                if added_kw:
                    answer += '\n\n' + ', '.join(added_kw) + ' 키워드가 추가되었습니다.'
            return jsonify({'status': 'ok', 'answer': answer, 'sources': similar_docs, 'added_keywords': added_kw})
        return jsonify({'status': 'error', 'answer': f'API 오류 (HTTP {resp.status_code})', 'sources': []})
    except Exception as e:
        return jsonify({'status': 'error', 'answer': f'오류가 발생했습니다: {str(e)}', 'sources': []})

@app.route('/insight-chat', methods=['POST'])
def insight_chat():
    """인사이트 챗봇 - 분석 + 수정 명령 처리"""
    import requests as req
    try:
        config = request.json or {}
        sid = config.get('sid', 's0')
        query = config.get('query', '')
        bk = config.get('bk', '')
        
        # 페르소나 데이터 로드
        persona_data = None
        persona_key = None
        try:
            resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"personas/{sid}/")
            if resp.get('Contents'):
                latest = sorted(resp['Contents'], key=lambda x: x['Key'], reverse=True)[0]
                persona_key = latest['Key']
                obj = s3.get_object(Bucket=S3_BUCKET, Key=persona_key)
                persona_data = json.loads(obj['Body'].read().decode('utf-8'))
        except:
            pass
        
        persona_json = json.dumps(persona_data.get('personas', []) if persona_data else [], ensure_ascii=False, indent=2)
        
        # RAG 검색
        similar_docs = search_similar(sid, query, top_k=5)
        
        # 클러스터별 원문 샘플 로드
        cluster_samples = ""
        try:
            cd = load_data(f"clusters_refined/{sid}/data_")
            if not cd: cd = load_data(f"clusters/{sid}/cluster_")
            if cd:
                cl_map = {}
                for it in cd:
                    c = it.get('cluster', 0)
                    if c not in cl_map: cl_map[c] = []
                    cl_map[c].append(it)
                for c in sorted(cl_map.keys()):
                    items = cl_map[c]
                    kw_cnt = {}
                    for it in items:
                        kw = it.get('kw','')
                        if kw: kw_cnt[kw] = kw_cnt.get(kw,0)+1
                    top_kw = sorted(kw_cnt.items(), key=lambda x:-x[1])[:5]
                    cluster_samples += f"\n클러스터 {c+1} ({len(items)}건, 주요키워드: {', '.join([k[0] for k in top_kw])}):\n"
                    for it in items[:2]:
                        cluster_samples += f"  - [{it.get('kw','')}] {it.get('title','')} | {it.get('desc','')[:100]}\n"
        except:
            pass
        rag_context = "\n".join([f"- {d.get('title','')} | {d.get('desc','')[:150]}" for d in similar_docs]) if similar_docs else "없음"
        
        # Claude에게 분석 또는 수정 명령 처리 요청
        prompt = f"""당신은 DCX 소비자 인사이트 전문가이자 데이터 편집 에이전트입니다.

## 현재 페르소나 데이터
{persona_json}

## 클러스터별 원문 샘플
{cluster_samples if cluster_samples else "없음"}

## RAG 검색 결과
{rag_context}

## 사용자 메시지
{query}

## 역할
사용자의 메시지를 분석해서 두 가지 중 하나를 수행하세요:

### A) 분석/질문인 경우
마케팅 인사이트, 전략 제안, 페르소나 분석 등을 답변하세요.
이 경우 JSON 블록 없이 텍스트만 응답하세요.

### B) 수정 명령인 경우 (예: "클러스터 합쳐줘", "페르소나 이름 바꿔줘", "인사이트 수정해줘")
1. 수정 사항을 설명하고
2. 반드시 아래 형식의 JSON 블록을 포함하세요:

```MODIFIED_DATA
[수정된 전체 페르소나 배열 JSON]
```

수정 시 규칙:
- 기존 데이터 구조(cluster_id, cluster_name, personas 배열) 유지
- 클러스터 합치기: 두 클러스터의 personas를 하나로 합치고 새 이름 부여
- 페르소나 수정: name, situation, pain_point, insight 필드 수정 가능
- 클러스터 삭제: 해당 클러스터를 배열에서 제거
- 응답은 한국어로
- 절대로 이모티콘, 이모지, 특수문자를 사용하지 마세요
- 마크다운 기호(**,##,###,- 불릿)도 사용하지 마세요
- 순수 텍스트 문장으로만 답변

절대로 이모티콘, 이모지, 특수문자(✅🔥💡📊 등)를 사용하지 마세요. 마크다운 기호(**,##,###,- 등)도 사용하지 마세요. 순수 텍스트 문장으로만 답변하세요. 한국어로 답변:"""

        resp = req.post(
            'https://api.anthropic.com/v1/messages',
            headers={'x-api-key': CLAUDE_API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
            json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 4000, 'messages': [{'role': 'user', 'content': prompt}]},
            timeout=120
        )
        
        if resp.status_code == 200:
            answer = resp.json()['content'][0]['text']
            modified = False
            
            # 수정 데이터가 있는지 확인
            import re
            mod_match = re.search(r'```MODIFIED_DATA\s*\n([\s\S]*?)\n```', answer)
            if mod_match:
                try:
                    new_personas = json.loads(mod_match.group(1))
                    if isinstance(new_personas, list) and len(new_personas) > 0:
                        # S3에 업데이트된 데이터 저장
                        if persona_data:
                            persona_data['personas'] = new_personas
                        else:
                            persona_data = {'bk': bk, 'personas': new_personas}
                        
                        from datetime import datetime
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        s3.put_object(
                            Bucket=S3_BUCKET,
                            Key=f"personas/{sid}/result_{ts}.json",
                            Body=json.dumps(persona_data, ensure_ascii=False).encode('utf-8')
                        )
                        # 메모리도 업데이트
                        persona_jobs[sid] = {'status': 'done', 'progress': 100, 'personas': new_personas}
                        modified = True
                except:
                    pass
            
            # 응답에서 MODIFIED_DATA 블록 제거
            clean_answer = re.sub(r'```MODIFIED_DATA\s*\n[\s\S]*?\n```', '', answer).strip()
            
            return jsonify({'status': 'ok', 'answer': clean_answer, 'modified': modified, 'sources': similar_docs})
        
        return jsonify({'status': 'error', 'answer': f'API 오류 (HTTP {resp.status_code})', 'modified': False, 'sources': []})
    except Exception as e:
        return jsonify({'status': 'error', 'answer': f'오류: {str(e)}', 'modified': False, 'sources': []})

@app.route('/sna-data/<sid>')
def get_sna_data(sid):
    """SNA 시각화용 데이터 반환"""
    try:
        # 페르소나 데이터 로드
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"personas/{sid}/")
        if not resp.get('Contents'):
            return jsonify({'status': 'error', 'error': 'no persona data'})
        
        latest = sorted(resp['Contents'], key=lambda x: x['Key'], reverse=True)[0]
        obj = s3.get_object(Bucket=S3_BUCKET, Key=latest['Key'])
        persona_data = json.loads(obj['Body'].read().decode('utf-8'))
        
        # 클러스터 데이터 로드
        all_data = load_data(f"clusters_refined/{sid}/data_")
        if not all_data:
            all_data = load_data(f"clusters/{sid}/cluster_")
        
        # SNA 노드 & 링크 생성
        nodes = []
        links = []
        
        # 중심 노드 (제품)
        bk = persona_data.get('bk', '제품')
        nodes.append({'id': 'center', 'name': bk, 'type': 'product', 'size': 40})
        
        # 클러스터 & 페르소나 노드
        for cluster in persona_data.get('personas', []):
            cid = cluster.get('cluster_id', 0)
            cname = cluster.get('cluster_name', f'클러스터{cid}')
            
            # 클러스터 노드
            cluster_node_id = f'cluster_{cid}'
            cluster_size = len([d for d in all_data if d.get('cluster') == cid-1])
            nodes.append({'id': cluster_node_id, 'name': cname, 'type': 'cluster', 'size': min(30, 15 + cluster_size//100)})
            links.append({'source': 'center', 'target': cluster_node_id, 'value': cluster_size})
            
            # 페르소나 노드
            for i, persona in enumerate(cluster.get('personas', [])):
                persona_node_id = f'persona_{cid}_{i}'
                nodes.append({
                    'id': persona_node_id, 
                    'name': persona.get('name', ''), 
                    'type': 'persona', 
                    'size': 12,
                    'pain_point': persona.get('pain_point', ''),
                    'insight': persona.get('insight', '')
                })
                links.append({'source': cluster_node_id, 'target': persona_node_id, 'value': 1})
        
        return jsonify({'status': 'ok', 'nodes': nodes, 'links': links, 'bk': bk})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/chat-ui')
def chat_ui():
    return send_from_directory('/home/ubuntu/cx-pipeline', 'chat.html')

@app.route('/dcx-chatbot')
def dcx_chatbot():
    return send_from_directory('/home/ubuntu/cx-pipeline', 'dcx-chatbot.html')

# ============ Keyword Generation (replaces n8n keyword steps) ============

@app.route('/generate-keywords', methods=['POST'])
def generate_keywords():
    """AI 키워드 생성 - n8n의 r1/r2/r3 로직을 서버에서 직접 처리"""
    import requests as req
    config = request.json
    bk = config.get('bk', '')
    problem_def = config.get('problemDef', '')
    existing_kw = config.get('existingKeywords', [])
    round_num = config.get('round', 1)
    
    if not bk:
        return jsonify({'status': 'error', 'error': 'bk (제품명) 필요'})
    
    existing_str = ', '.join(existing_kw) if existing_kw else '없음'
    
    if round_num == 1:
        ages_str = ', '.join(config.get('ages', [])) if config.get('ages') else ''
        age_range_str = ', '.join(config.get('ageRange', [])) if config.get('ageRange') else ''
        gens_str = ', '.join(config.get('gens', [])) if config.get('gens') else ''
        target_desc = ' | '.join(filter(None, [ages_str, age_range_str, gens_str])) or '전체'
        
        prompt = f"""제품/서비스: "{bk}"
문제정의: {problem_def or '소비자 경험 분석'}
타겟: {target_desc}

당신은 소비자 경험(CX) 리서치 전문가입니다.
네이버 카페에서 "{bk}" 관련 소비자의 숨겨진 경험과 니치한 맥락을 발굴하기 위한 검색 키워드를 생성하세요.

## 키워드 형태 규칙 (매우 중요!)
- 반드시 1~2단어 (최대 3글자 단어 2개)
- 명사, 형용사 위주
- 문장 형태 절대 금지! "일요일도 연락", "휴가중 전화" 같은 문장/구절은 안됨
- 좋은 예: 누수, 화재, 단열, 소음, 곰팡이, 환기, 습도, 결로, 균열
- 나쁜 예: 보험 후기, 보험 비교, 보험 추천

## 절대 금지 키워드
후기, 비교, 추천, 가격, 장단점, 선택, 고민, 리뷰, 평가, 만족, 불만

## 키워드 방향 (문제정의 중심)
- 문제정의에서 출발하여 소비자가 겪는 구체적 상황/사물/현상을 나타내는 단어
- Pain Point 키워드 필수: 불편, 실패, 후회, 걱정, 고장, 분쟁 등 소비자 고통을 드러내는 단어
- "{bk} + [키워드]"로 네이버 카페 검색 시 실제 경험담이 나올 법한 단어
- 에어컨 예시: 습도, 온도, 추위, 환기, 화초, 소음, 쾌적, 타이머, 렌탈, 단열, 결로, 곰팡이, 수면, 외출, 집콕, 요리, 더위, 신혼, 자취, 재택, 강아지, 고양이, 신생아, 임산부
- 보험 예시: 누수, 화재, 침수, 균열, 도난, 분실, 사고, 골절, 입원, 수술, 통원, 약관, 면책, 갱신, 해지, 실손, 치아, 임신, 출산, 노후

## 카테고리 분류
- 상황맥락: 소비자가 처한 구체적 상황
- 감정표현: 감정/심리 상태
- 문제상황: 예상 못한 문제/트러블
- 숨은니즈: 잘 드러나지 않는 니즈
- 타겟특화: {target_desc} 특유의 맥락
- 시즌시간: 계절, 시간대, 시기 관련
- 공간장소: 특정 공간이나 장소

## 출력 (JSON 배열만, 설명 없이)
[{{"kw": "키워드", "cat": "카테고리"}}]

각 카테고리당 최소 12개씩, 총 70개 이상 생성. 카테고리당 1-2개만 나오면 안됨:"""
    else:
        prompt = f"""제품: "{bk}"
문제정의: {problem_def or '소비자 경험 분석'}
기존 키워드: {existing_str}

기존 키워드와 중복되지 않는 새 키워드를 생성하세요.

## 규칙
- "후기/비교/추천/가격/선택/고민" 같은 흔한 키워드 절대 금지
- 소비자의 구체적 상황, 감정, 에피소드를 드러내는 니치한 키워드
- 반드시 1~2단어 명사/형용사. 문장 금지!
- "{bk} + [키워드]"로 크롤링하므로 키워드에 "{bk}" 포함 금지
- 더 깊고, 더 구체적이고, 더 예상 밖의 소비자 경험 맥락

[{{"kw": "키워드", "cat": "카테고리"}}]

각 카테고리당 최소 15개씩, 총 100개 이상 생성. 카테고리당 1-2개만 나오면 절대 안됨. 다양하고 풍부하게. JSON만 출력:"""
    
    try:
        resp = req.post(
            'https://api.anthropic.com/v1/messages',
            headers={'x-api-key': CLAUDE_API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
            json={'model': 'claude-sonnet-4-20250514', 'max_tokens': 8000, 'messages': [{'role': 'user', 'content': prompt}]},
            timeout=120
        )
        if resp.status_code == 200:
            text = resp.json()['content'][0]['text']
            match = re.search(r'\[[\s\S]*\]', text)
            if match:
                keywords = json.loads(match.group())
                # Score keywords by searching Naver
                scored = []
                for i, kw_obj in enumerate(keywords):
                    kw = kw_obj.get('kw', '')
                    cat = kw_obj.get('cat', '')
                    if not kw or len(kw) < 2:
                        continue
                    # Skip if duplicate
                    if kw.lower() in [e.lower() for e in existing_kw]:
                        continue
                    # Quick score via Naver search
                    score = 50
                    try:
                        nr = req.get('https://openapi.naver.com/v1/search/cafearticle.json',
                            headers={'X-Naver-Client-Id': NAVER_CLIENT_ID, 'X-Naver-Client-Secret': NAVER_CLIENT_SECRET},
                            params={'query': f'{bk} {kw}', 'display': 1}, timeout=3)
                        total = nr.json().get('total', 0)
                        if total >= 10000: score = 95
                        elif total >= 5000: score = 85
                        elif total >= 1000: score = 75
                        elif total >= 500: score = 65
                        elif total >= 100: score = 55
                        elif total >= 50: score = 45
                        elif total >= 10: score = 35
                        else: score = 25
                    except:
                        pass
                    scored.append({'id': i+1, 'kw': kw, 'cat': cat, 'score': score, 'total': total if 'total' in dir() else 0})
                    # Rate limit
                    if i % 5 == 4:
                        import time; time.sleep(0.1)
                
                scored.sort(key=lambda x: -x.get('score', 0))
                return jsonify({'status': 'ok', 'keywords': scored, 'round': round_num})
        return jsonify({'status': 'error', 'error': 'Claude API 응답 파싱 실패'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/delete-session/<sid>', methods=['DELETE'])
def delete_session(sid):
    """세션 삭제"""
    try:
        # Delete session file
        s3.delete_object(Bucket=S3_BUCKET, Key=f"sessions/{sid}/session.json")
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/pipeline-status/<sid>')
def pipeline_status(sid):
    """한번에 모든 파이프라인 상태 조회"""
    result = {
        'session': None,
        'crawl': jobs.get(sid, {'status': 'not_found'}),
        'preprocess': preprocess_jobs.get(sid, {'status': 'not_found'}),
        'train': train_jobs.get(sid, {'status': 'not_found'}),
        'cluster': cluster_jobs.get(sid, {'status': 'not_found'}),
        'embed': embed_jobs.get(sid, {'status': 'not_found'}),
        'persona': persona_jobs.get(sid, {'status': 'not_found'})
    }
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=f"sessions/{sid}/session.json")
        result['session'] = json.loads(obj['Body'].read().decode('utf-8'))
    except:
        pass
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
