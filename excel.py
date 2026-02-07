import streamlit as st
import pandas as pd
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="Town Construct Report Generator", layout="wide")
st.title("📊 Automated Town Construct Report (Final)")
st.markdown("""
**System Status:** Optimized.
**Logic:**
1.  **Dynamic:** Only shows stratifications present in the file (e.g., removes Large Town if empty).
2.  **TVS:** Primary (MD) vs Secondary (ASD).
3.  **Additions:** Primary (MD/Branch) vs Secondary (ASD).
4.  **Deep Rural:** 'WIP' treated as Vacant.
5.  **Precision:** Integer rounding for exact volume matching.
""")

# --- 1. CLASSIFICATION LOGIC ---

def get_bal_category(x):
    if pd.isna(x): return 'Vacant'
    s = str(x).lower().strip()
    if 'wip' in s: return 'Vacant' # Deep Rural Logic
    if s == '' or s == 'nan' or 'vacant' in s: return 'Vacant'
    
    if 'md' in s or 'primary' in s or 'branch' in s: return 'Pri Store'
    if 'asd' in s: return 'ASD'
    return 'Vacant'

def get_tvs_category(x):
    if pd.isna(x): return 'Vacant'
    s = str(x).lower().strip()
    if 'md' in s or 'primary' in s: return 'MD'
    if 'asd' in s: return 'ASD'
    return 'Other'

# --- 2. INTERVENTION LOGIC ---

def get_addition_type(row):
    intervention = str(row.get('Network Intervention', '')).strip()
    nature = str(row.get('Nature of Intervention', '')).strip()
    
    is_add = False
    if intervention == 'Yes': is_add = True
    elif 'opportunity' in nature.lower(): is_add = True
        
    if not is_add: return None
        
    if 'branch' in nature.lower() or 'md' in nature.lower() or 'primary' in nature.lower():
        return 'Primary'
    return 'Secondary'

def get_reduction_type(row):
    intervention = str(row.get('Network Intervention', '')).strip()
    bal_cat = get_bal_category(row.get('BAL Store Type')) 
    
    if intervention == 'Replacement':
        if bal_cat == 'Pri Store': return 'Primary'
        elif bal_cat == 'ASD': return 'Secondary'
    return None

# --- 3. GAP LOGIC ---

def is_store_gap(row):
    bal_cat = get_bal_category(row.get('BAL Store Type'))
    intervention = str(row.get('Network Intervention', '')).strip()
    nature = str(row.get('Nature of Intervention', '')).strip()
    
    if bal_cat == 'Vacant':
        if intervention == 'Yes' or 'opportunity' in nature.lower():
            return 1
    return 0

def is_unique_gap(row):
    bal_cat = get_bal_category(row.get('BAL Store Type'))
    if bal_cat == 'Vacant': return 1
    return 0

# --- 4. MAIN PROCESSOR ---

def process_file(uploaded_file):
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, header=1)
        else:
            df = pd.read_excel(uploaded_file, header=1)
        
        if 'Updated Stratification' not in df.columns:
            uploaded_file.seek(0)
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file, header=0)
            else:
                df = pd.read_excel(uploaded_file, header=0)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None

    df.columns = df.columns.str.strip().str.replace('\n', ' ')
    
    # Identify Volume Columns
    tvs_vol_col = 'TVS S1 Vol' if 'TVS S1 Vol' in df.columns else 'TVS S1 Vol Basis MS'
    
    # Pre-Round Volumes to Integers (Critical for exact match)
    df['S1 Ind - F Vistaar'] = df['S1 Ind - F Vistaar'].fillna(0).round(0).astype(int)
    df['BAL S1 Vol - Vistaar'] = df['BAL S1 Vol - Vistaar'].fillna(0).round(0).astype(int)
    if tvs_vol_col in df.columns:
        df[tvs_vol_col] = df[tvs_vol_col].fillna(0).round(0).astype(int)
    else:
        df[tvs_vol_col] = 0

    # DYNAMIC CATEGORY DETECTION
    # Define standard order, but only keep what is in the file
    standard_order = ['Large Town', 'Small Town', 'Rural', 'Deep Rural']
    present_strats = df['Updated Stratification'].dropna().unique()
    categories = [cat for cat in standard_order if cat in present_strats]
    
    # If file has non-standard categories, append them at the end
    for cat in present_strats:
        if cat not in standard_order:
            categories.append(cat)

    output_rows = []

    for strat in categories:
        subset = df[df['Updated Stratification'] == strat]
        
        buckets = {'Pri Store': [], 'ASD': [], 'Vacant': []}
        for idx, row in subset.iterrows():
            cat = get_bal_category(row['BAL Store Type'])
            buckets[cat].append(idx)
            
        # Stratification Totals
        tot_bal = 0
        tot_tvs_pri = 0
        tot_tvs_sec = 0
        tot_add_pri = 0
        tot_add_sec = 0
        tot_red_pri = 0
        tot_red_sec = 0
        tot_store_gap = 0
        tot_unique_gap = 0
        
        for idx, row in subset.iterrows():
            bal_cat = get_bal_category(row['BAL Store Type'])
            tvs_cat = get_tvs_category(row['TVS Store Type'])
            
            if bal_cat != 'Vacant': tot_bal += 1
            if tvs_cat == 'MD': tot_tvs_pri += 1
            elif tvs_cat == 'ASD': tot_tvs_sec += 1
            
            add_type = get_addition_type(row)
            if add_type == 'Primary': tot_add_pri += 1
            elif add_type == 'Secondary': tot_add_sec += 1
            
            red_type = get_reduction_type(row)
            if red_type == 'Primary': tot_red_pri += 1
            elif red_type == 'Secondary': tot_red_sec += 1
            
            tot_store_gap += is_store_gap(row)
            tot_unique_gap += is_unique_gap(row)

        row_order = ['Pri Store', 'ASD', 'Vacant', 'Total']
        
        for i, rtype in enumerate(row_order):
            label = strat if i == 0 else ''
            
            if rtype == 'Total':
                row_data = subset
                cnt_bal = tot_bal
                cnt_tvs_p = tot_tvs_pri
                cnt_tvs_s = tot_tvs_sec
                cnt_add_p = tot_add_pri
                cnt_add_s = tot_add_sec
                cnt_red_p = tot_red_pri
                cnt_red_s = tot_red_sec
                cnt_store_gap = tot_store_gap
                cnt_unique_gap = tot_unique_gap
            else:
                indices = buckets[rtype]
                row_data = df.loc[indices]
                cnt_bal = len(indices) if rtype != 'Vacant' else 0
                
                cnt_tvs_p = 0
                cnt_tvs_s = 0
                cnt_add_p = 0
                cnt_add_s = 0
                cnt_red_p = 0
                cnt_red_s = 0
                cnt_store_gap = 0
                cnt_unique_gap = 0
                
                for _, sub_row in row_data.iterrows():
                    t_cat = get_tvs_category(sub_row['TVS Store Type'])
                    if t_cat == 'MD': cnt_tvs_p += 1
                    elif t_cat == 'ASD': cnt_tvs_s += 1
                    
                    a_type = get_addition_type(sub_row)
                    if a_type == 'Primary': cnt_add_p += 1
                    elif a_type == 'Secondary': cnt_add_s += 1
                    
                    r_type = get_reduction_type(sub_row)
                    if r_type == 'Primary': cnt_red_p += 1
                    elif r_type == 'Secondary': cnt_red_s += 1
                    
                    cnt_store_gap += is_store_gap(sub_row)
                    cnt_unique_gap += is_unique_gap(sub_row)

            # Post Gap
            cnt_post_gap = max(0, cnt_unique_gap - (cnt_add_p + cnt_add_s))

            # Metrics
            ind_s1 = row_data['S1 Ind - F Vistaar'].sum()
            bal_vol = row_data['BAL S1 Vol - Vistaar'].sum()
            tvs_vol = row_data[tvs_vol_col].sum()
            
            bal_ms = bal_vol / ind_s1 if ind_s1 > 0 else 0
            vol_gap = tvs_vol - bal_vol
            
            if bal_vol > 0:
                cr = tvs_vol / bal_vol
                cr_display = round(cr, 1)
            else:
                cr_display = '-'

            def fmt(v): return int(v)

            new_row = {
                'Stratification': label,
                '# Store Count': rtype,
                'BAL': cnt_bal,
                'TVS (Primary)': cnt_tvs_p,
                'TVS (Secondary)': cnt_tvs_s,
                'Store Gap': cnt_store_gap, 
                'Unique Location Gap': cnt_unique_gap, 
                'IND S1': fmt(ind_s1),
                'S1 BAL Vol': fmt(bal_vol),
                'BAL MS': f"{round(bal_ms * 100)}%",
                'S1 TVS Vol': fmt(tvs_vol),
                'Vol Gap (TVS-BAL)': fmt(vol_gap),
                'CR': cr_display,
                'Addition (Primary)': cnt_add_p,
                'Addition (Secondary)': cnt_add_s,
                'Reduction (Primary)': cnt_red_p,
                'Reduction (Secondary)': cnt_red_s,
                'BAL Network Count @ UP 2.0': 0,
                'Unique Location Gap post appointment': cnt_post_gap
            }
            output_rows.append(new_row)

    # Grand Total
    df_out = pd.DataFrame(output_rows)
    grand_total = {
        'Stratification': 'Total',
        '# Store Count': 'Total',
        'BAL': df_out[df_out['# Store Count'] == 'Total']['BAL'].sum(),
        'TVS (Primary)': df_out[df_out['# Store Count'] == 'Total']['TVS (Primary)'].sum(),
        'TVS (Secondary)': df_out[df_out['# Store Count'] == 'Total']['TVS (Secondary)'].sum(),
        'Store Gap': df_out[df_out['# Store Count'] == 'Total']['Store Gap'].sum(),
        'Unique Location Gap': df_out[df_out['# Store Count'] == 'Total']['Unique Location Gap'].sum(),
        'IND S1': df_out[df_out['# Store Count'] == 'Total']['IND S1'].sum(),
        'S1 BAL Vol': df_out[df_out['# Store Count'] == 'Total']['S1 BAL Vol'].sum(),
        'S1 TVS Vol': df_out[df_out['# Store Count'] == 'Total']['S1 TVS Vol'].sum(),
        'Vol Gap (TVS-BAL)': df_out[df_out['# Store Count'] == 'Total']['Vol Gap (TVS-BAL)'].sum(),
        'Addition (Primary)': df_out[df_out['# Store Count'] == 'Total']['Addition (Primary)'].sum(),
        'Addition (Secondary)': df_out[df_out['# Store Count'] == 'Total']['Addition (Secondary)'].sum(),
        'Reduction (Primary)': df_out[df_out['# Store Count'] == 'Total']['Reduction (Primary)'].sum(),
        'Reduction (Secondary)': df_out[df_out['# Store Count'] == 'Total']['Reduction (Secondary)'].sum(),
        'Unique Location Gap post appointment': df_out[df_out['# Store Count'] == 'Total']['Unique Location Gap post appointment'].sum(),
    }
    
    if grand_total['IND S1'] > 0:
        grand_total['BAL MS'] = f"{round((grand_total['S1 BAL Vol'] / grand_total['IND S1']) * 100)}%"
    else:
        grand_total['BAL MS'] = "0%"
    
    if grand_total['S1 BAL Vol'] > 0:
        grand_total['CR'] = round(grand_total['S1 TVS Vol'] / grand_total['S1 BAL Vol'], 1)
    else:
        grand_total['CR'] = '-'
        
    grand_total['BAL Network Count @ UP 2.0'] = 0
    
    # Append Total
    df_out = pd.concat([df_out, pd.DataFrame([grand_total])], ignore_index=True)
    
    return df_out

# --- UI ---
uploaded_file = st.file_uploader("Upload Intermediate File (Excel/CSV)", type=['xlsx', 'csv'])

if uploaded_file:
    st.success("File uploaded! Processing...")
    df_result = process_file(uploaded_file)
    
    if df_result is not None:
        st.subheader("Preview")
        st.dataframe(df_result)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False)
            
        st.download_button(
            label="📥 Download Excel Report",
            data=buffer.getvalue(),
            file_name="Slide_Template_Exact.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )