# Face Safety App – Fixed Starter Package

এই ZIP-এ Streamlit + Supabase ভিত্তিক একটি সম্পূর্ণ runnable starter implementation রয়েছে।

## ফিচার
- Supabase email/password signup ও login
- User profile ও public username সংরক্ষণ
- Consent grant এবং withdrawal history
- Consent ছাড়া selfie upload বন্ধ
- Private Supabase Storage-এ selfie রাখার ব্যবস্থা
- NewsAPI দিয়ে public news search (API key প্রয়োজন)
- Username/full-name candidate matching
- Optional Toxic-BERT text review
- Manual text review এবং findings সংরক্ষণ
- User-scoped Row Level Security schema
- Personal profile/findings deletion workflow

**গুরুত্বপূর্ণ সীমাবদ্ধতা:** এই package face recognition, face matching, liveness detection বা কোনো ব্যক্তির পরিচয় যাচাই করে না। News matching কেবল সম্ভাব্য candidate দেখায়। AI score প্রমাণ নয়; মানুষের review আবশ্যক।

## 1. Python environment (Windows PowerShell)

```powershell
cd Face_Safety_App_Fixed
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Execution Policy error হলে:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## 2. Supabase setup

1. Supabase project তৈরি করুন।
2. SQL Editor খুলুন।
3. `supabase/schema.sql` সম্পূর্ণ run করুন।
4. Storage-এ `selfies` নামে **Private** bucket তৈরি করুন।
5. `selfies` bucket-এর authenticated storage policy এমনভাবে configure করুন যেন user কেবল নিজের `{auth.uid()}/...` folder access করতে পারে।
6. Authentication settings-এ email confirmation চালু থাকলে signup-এর পর email confirm করুন।

## 3. Secrets configure

`.streamlit/secrets.toml.example` কপি করে `.streamlit/secrets.toml` নামে রাখুন।

সেখানে বসান:
- Supabase Project URL
- Supabase publishable/anon key (service_role নয়)
- NewsAPI key (news feature ব্যবহার করলে)

**secrets.toml GitHub-এ commit করবেন না।**

## 4. Run

```powershell
python -m py_compile app.py
streamlit run app.py
```

Browser: http://localhost:8501

## 5. Optional Toxic-BERT

শুধু text model ব্যবহার করতে চাইলে:

```powershell
pip install transformers torch
```

প্রথমবার model download হবে। RAM/ডিস্ক ও internet প্রয়োজন। Model unavailable হলে app keyword fallback ব্যবহার করে; এটি নির্ভরযোগ্য abuse classifier নয়।

## 6. GitHub upload

```powershell
git init
git add .
git status
git commit -m "Add fixed Face Safety App starter"
```

`git status`-এ `.streamlit/secrets.toml` যেন না থাকে তা নিশ্চিত করুন।

## 7. Known limitations / production checklist

- NewsAPI free plan-এর query/coverage সীমা থাকতে পারে।
- News search এখানে English NewsAPI query ব্যবহার করে।
- Matching false positive দিতে পারে; নাম/username match identity proof নয়।
- Storage bucket private রাখুন এবং নিজের folder-এ access সীমাবদ্ধ করুন।
- Supabase Auth email confirmation ও password policy configure করুন।
- Production-এর আগে backup, retention, deletion verification, audit logging, rate limiting, legal/privacy review এবং security testing করুন।
- Consent withdrawal-এর পর storage cleanup ব্যর্থ হলে Supabase Storage-এ manually verify করুন।
- Account deletion (Auth user) এই app থেকে করা হয় না; Supabase Auth account deletion আলাদা admin/secure server-side workflow প্রয়োজন।

## Troubleshooting

### `ModuleNotFoundError`
```powershell
pip install -r requirements.txt
```

### Supabase `Invalid API key`
URL এবং anon/publishable key যাচাই করুন। service_role key ব্যবহার করবেন না।

### RLS error
`supabase/schema.sql` run হয়েছে কি না এবং user authenticated কি না যাচাই করুন।

### News search fails
NewsAPI key, quota, internet এবং API response যাচাই করুন।

### `py_compile` error
```powershell
python -m py_compile app.py
```
সম্পূর্ণ traceback সংরক্ষণ করে developer-কে দিন।
