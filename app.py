from flask import Flask, render_template, request, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import os
from io import BytesIO
from dateutil.relativedelta import relativedelta
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Database Model for Categories
class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_date = db.Column(db.Date, default=datetime.now().date)
    description = db.Column(db.String(200))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'created_date': self.created_date.strftime('%Y-%m-%d') if self.created_date else '',
            'description': self.description or ''
        }

# Database Model for Assets
class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_no = db.Column(db.String(50), unique=True, nullable=False)
    asset_category = db.Column(db.String(100), nullable=False, default='Uncategorized')
    description = db.Column(db.String(200), nullable=False)
    user = db.Column(db.String(100), nullable=False)
    serial_no = db.Column(db.String(100))
    condition = db.Column(db.String(50), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    depreciation_start_date = db.Column(db.Date, nullable=False)
    useful_life_yrs = db.Column(db.Float, nullable=False)
    disposal_date = db.Column(db.Date)
    initial_cost = db.Column(db.Float, nullable=False)
    other_cost = db.Column(db.Float, default=0.0)
    entity = db.Column(db.String(100), nullable=False)
    currency = db.Column(db.String(3), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'asset_no': self.asset_no,
            'asset_category': self.asset_category,
            'description': self.description,
            'user': self.user,
            'serial_no': self.serial_no,
            'condition': self.condition,
            'purchase_date': self.purchase_date.strftime('%Y-%m-%d') if self.purchase_date else '',
            'depreciation_start_date': self.depreciation_start_date.strftime(
                '%Y-%m-%d') if self.depreciation_start_date else '',
            'useful_life_yrs': self.useful_life_yrs,
            'disposal_date': self.disposal_date.strftime('%Y-%m-%d') if self.disposal_date else '',
            'initial_cost': self.initial_cost,
            'other_cost': self.other_cost,
            'entity': self.entity,
            'currency': self.currency
        }

# Create tables and initialize database
with app.app_context():
    db.create_all()
    print("✓ Database tables created")

    default_categories = ['Electronics', 'Furniture', 'Vehicles', 'Machinery',
                          'Software', 'Office Equipment', 'Building', 'IT Equipment']

    for cat_name in default_categories:
        existing = Category.query.filter_by(name=cat_name).first()
        if not existing:
            category = Category(name=cat_name, created_date=datetime.now().date())
            db.session.add(category)
            print(f"✓ Added default category: {cat_name}")

    uncat = Category.query.filter_by(name='Uncategorized').first()
    if not uncat:
        uncategorized = Category(name='Uncategorized', created_date=datetime.now().date())
        db.session.add(uncategorized)
        print("✓ Added default category: Uncategorized")

    db.session.commit()
    print("✓ Default categories initialized")

# Helper function to format numbers with commas
def format_currency(amount):
    return f"{amount:,.2f}"

# ==================== DEPRECIATION CALCULATION FUNCTIONS ====================

def calculate_asset_depreciation(asset):
    """Calculate straight-line depreciation for an asset using MONTHS"""
    total_cost = asset.initial_cost + asset.other_cost
    annual_depreciation = total_cost / asset.useful_life_yrs if asset.useful_life_yrs > 0 else 0
    monthly_depreciation = annual_depreciation / 12

    if asset.disposal_date:
        end_date = asset.disposal_date
    else:
        end_date = datetime.now().date()

    if asset.disposal_date:
        months_diff = (asset.disposal_date.year - asset.depreciation_start_date.year) * 12 + (
                    asset.disposal_date.month - asset.depreciation_start_date.month)
    else:
        months_diff = (datetime.now().date().year - asset.depreciation_start_date.year) * 12 + (
                    datetime.now().date().month - asset.depreciation_start_date.month)

    total_months = asset.useful_life_yrs * 12
    months_diff = min(months_diff, total_months)

    accumulated_depreciation = monthly_depreciation * months_diff
    accumulated_depreciation = min(accumulated_depreciation, total_cost)
    net_book_value = total_cost - accumulated_depreciation

    yearly_breakdown = []
    current_date = asset.depreciation_start_date
    months_elapsed = 0

    for year in range(1, int(asset.useful_life_yrs) + 1):
        year_depreciation = 0
        year_start = current_date
        year_end = current_date.replace(year=current_date.year + 1)

        months_in_year = 12
        if asset.disposal_date and asset.disposal_date < year_end:
            months_in_year = (asset.disposal_date.year - current_date.year) * 12 + (
                        asset.disposal_date.month - current_date.month)
            months_in_year = max(0, months_in_year)

        year_depreciation = monthly_depreciation * months_in_year

        total_depreciated = sum(d['depreciation'] for d in yearly_breakdown) + year_depreciation
        if total_depreciated > total_cost:
            year_depreciation = total_cost - sum(d['depreciation'] for d in yearly_breakdown)

        months_elapsed += months_in_year
        accumulated = monthly_depreciation * months_elapsed

        yearly_breakdown.append({
            'asset_no': asset.asset_no,
            'description': asset.description,
            'year': year,
            'year_start': current_date.strftime('%Y-%m-%d'),
            'year_end': year_end.strftime('%Y-%m-%d'),
            'depreciation': round(year_depreciation, 2),
            'accumulated_depreciation': round(min(accumulated, total_cost), 2),
            'net_book_value': round(max(total_cost - accumulated, 0), 2)
        })

        current_date = year_end
        if asset.disposal_date and current_date > asset.disposal_date:
            break

    return {
        'asset': asset,
        'total_cost': total_cost,
        'annual_depreciation': round(annual_depreciation, 2),
        'monthly_depreciation': round(monthly_depreciation, 2),
        'accumulated_depreciation': round(accumulated_depreciation, 2),
        'net_book_value': round(net_book_value, 2),
        'depreciation_percentage': round((accumulated_depreciation / total_cost) * 100, 2) if total_cost > 0 else 0,
        'months_elapsed': months_diff,
        'total_months': total_months,
        'yearly_breakdown': yearly_breakdown,
        'is_active': not asset.disposal_date
    }

def calculate_asset_movement(asset, start_date, end_date):
    """Calculate asset movement for a specific period using MONTHS"""
    total_cost = asset.initial_cost + asset.other_cost
    annual_depreciation = total_cost / asset.useful_life_yrs if asset.useful_life_yrs > 0 else 0
    monthly_depreciation = annual_depreciation / 12

    # IMPORTANT: Use ONLY depreciation start date for depreciation calculation
    # Purchase date only affects when asset appears in COST section
    depreciation_start = asset.depreciation_start_date

    # Determine COST movement based on PURCHASE date
    if asset.purchase_date <= end_date:
        if asset.purchase_date < start_date:
            cost_opening = total_cost
            cost_additions = 0
        else:
            cost_opening = 0
            cost_additions = total_cost
    else:
        cost_opening = 0
        cost_additions = 0

    # Determine if asset was disposed during the period
    if asset.disposal_date:
        if asset.disposal_date < start_date:
            cost_opening = 0
            cost_additions = 0
            cost_disposals = 0
            is_active_during_period = False
        elif asset.disposal_date <= end_date:
            cost_opening = total_cost if asset.purchase_date < start_date else 0
            cost_additions = total_cost if start_date <= asset.purchase_date <= end_date else 0
            cost_disposals = total_cost
            is_active_during_period = True
        else:
            cost_opening = total_cost if asset.purchase_date < start_date else 0
            cost_additions = total_cost if start_date <= asset.purchase_date <= end_date else 0
            cost_disposals = 0
            is_active_during_period = True
    else:
        cost_opening = total_cost if asset.purchase_date < start_date else 0
        cost_additions = total_cost if start_date <= asset.purchase_date <= end_date else 0
        cost_disposals = 0
        is_active_during_period = True

    cost_closing = cost_opening + cost_additions - cost_disposals

    # ========== DEPRECIATION CALCULATION - Using ONLY depreciation_start date ==========

    # Depreciation opening (up to start date)
    if depreciation_start < start_date:
        # Calculate months from depreciation start to period start
        months_to_start = (start_date.year - depreciation_start.year) * 12 + (
                    start_date.month - depreciation_start.month)
        months_to_start = max(0, months_to_start)
        depn_opening = min(monthly_depreciation * months_to_start, total_cost)
    else:
        depn_opening = 0

    # Depreciation for the period - THIS IS THE KEY
    # The depreciation period starts at the LATER of: period start OR depreciation start
    period_start = max(start_date, depreciation_start)
    period_end = min(end_date, asset.disposal_date if asset.disposal_date else end_date)

    if period_end >= period_start and is_active_during_period:
        # Calculate months difference
        months_in_period = (period_end.year - period_start.year) * 12 + (period_end.month - period_start.month)

        # Add 1 month if there are any days in the period (partial month handling)
        if period_end > period_start:
            months_in_period += 1

        months_in_period = max(0, months_in_period)
        depn_period = min(monthly_depreciation * months_in_period, total_cost - depn_opening)
    else:
        depn_period = 0

    # Depreciation on disposals
    if asset.disposal_date and start_date <= asset.disposal_date <= end_date:
        months_to_disposal = (asset.disposal_date.year - depreciation_start.year) * 12 + (
                    asset.disposal_date.month - depreciation_start.month)
        months_to_disposal = max(0, months_to_disposal)
        depn_up_to_disposal = min(monthly_depreciation * months_to_disposal, total_cost)
        depn_disposals = max(0, depn_up_to_disposal - depn_opening)
    else:
        depn_disposals = 0

    # Depreciation closing
    depn_closing = depn_opening + depn_period - depn_disposals

    # Net Book Values
    nbv_opening = cost_opening - depn_opening
    nbv_closing = cost_closing - depn_closing

    return {
        'asset_id': asset.id,
        'asset_no': asset.asset_no,
        'description': asset.description,
        'user': asset.user,
        'entity': asset.entity,
        'currency': asset.currency,
        'purchase_date': asset.purchase_date.strftime('%Y-%m-%d'),
        'disposal_date': asset.disposal_date.strftime('%Y-%m-%d') if asset.disposal_date else '',
        'cost_opening': round(cost_opening, 2),
        'cost_additions': round(cost_additions, 2),
        'cost_disposals': round(cost_disposals, 2),
        'cost_closing': round(cost_closing, 2),
        'depn_opening': round(depn_opening, 2),
        'depn_period': round(depn_period, 2),
        'depn_disposals': round(depn_disposals, 2),
        'depn_closing': round(depn_closing, 2),
        'nbv_opening': round(nbv_opening, 2),
        'nbv_closing': round(nbv_closing, 2)
    }


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/assets')
def get_assets():
    assets = Asset.query.all()
    return jsonify([asset.to_dict() for asset in assets])

@app.route('/api/assets', methods=['POST'])
def add_asset():
    try:
        data = request.json
        asset = Asset(
            asset_no=data['asset_no'],
            asset_category=data.get('asset_category', 'Uncategorized'),
            description=data['description'],
            user=data['user'],
            serial_no=data.get('serial_no', ''),
            condition=data['condition'],
            purchase_date=datetime.strptime(data['purchase_date'], '%Y-%m-%d').date(),
            depreciation_start_date=datetime.strptime(data['depreciation_start_date'], '%Y-%m-%d').date(),
            useful_life_yrs=float(data['useful_life_yrs']),
            disposal_date=datetime.strptime(data['disposal_date'], '%Y-%m-%d').date() if data.get(
                'disposal_date') else None,
            initial_cost=float(data['initial_cost']),
            other_cost=float(data.get('other_cost', 0)),
            entity=data['entity'],
            currency=data['currency']
        )
        db.session.add(asset)
        db.session.commit()
        return jsonify({'success': True, 'asset': asset.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/assets/<int:asset_id>', methods=['PUT'])
def update_asset(asset_id):
    try:
        asset = Asset.query.get_or_404(asset_id)
        data = request.json

        asset.asset_no = data['asset_no']
        asset.asset_category = data.get('asset_category', 'Uncategorized')
        asset.description = data['description']
        asset.user = data['user']
        asset.serial_no = data.get('serial_no', '')
        asset.condition = data['condition']
        asset.purchase_date = datetime.strptime(data['purchase_date'], '%Y-%m-%d').date()
        asset.depreciation_start_date = datetime.strptime(data['depreciation_start_date'], '%Y-%m-%d').date()
        asset.useful_life_yrs = float(data['useful_life_yrs'])
        asset.disposal_date = datetime.strptime(data['disposal_date'], '%Y-%m-%d').date() if data.get(
            'disposal_date') else None
        asset.initial_cost = float(data['initial_cost'])
        asset.other_cost = float(data.get('other_cost', 0))
        asset.entity = data['entity']
        asset.currency = data['currency']

        db.session.commit()
        return jsonify({'success': True, 'asset': asset.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/assets/<int:asset_id>', methods=['DELETE'])
def delete_asset(asset_id):
    try:
        asset = Asset.query.get_or_404(asset_id)
        db.session.delete(asset)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== EXPORT/IMPORT ROUTES ====================

@app.route('/export/excel')
def export_excel():
    assets = Asset.query.all()
    data = [asset.to_dict() for asset in assets]

    if not data:
        df = pd.DataFrame(columns=['ASSET NO.', 'ASSET CATEGORY', 'DESCRIPTION', 'USER', 'SERIAL NO.', 'CONDITION',
                                   'Purchase Date', 'Depreciation Start Date', 'Useful life (Yrs)',
                                   'DISPOSAL Date', 'INITIAL COST', 'OTHER COST', 'Entity', 'Currency'])
    else:
        df = pd.DataFrame(data)
        if 'id' in df.columns:
            df = df.drop('id', axis=1)

        column_order = ['asset_no', 'asset_category', 'description', 'user', 'serial_no', 'condition',
                        'purchase_date', 'depreciation_start_date', 'useful_life_yrs',
                        'disposal_date', 'initial_cost', 'other_cost', 'entity', 'currency']

        df = df[column_order]
        df.columns = ['ASSET NO.', 'ASSET CATEGORY', 'DESCRIPTION', 'USER', 'SERIAL NO.', 'CONDITION',
                      'Purchase Date', 'Depreciation Start Date', 'Useful life (Yrs)',
                      'DISPOSAL Date', 'INITIAL COST', 'OTHER COST', 'Entity', 'Currency']

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Assets', index=False)

        worksheet = writer.sheets['Assets']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'asset_register_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/download/template')
def download_template():
    template_data = {
        'ASSET NO.': ['A001', 'A002'],
        'ASSET CATEGORY': ['Electronics', 'Furniture'],
        'DESCRIPTION': ['Laptop Dell XPS', 'Office Chair'],
        'USER': ['John Doe', 'Jane Smith'],
        'SERIAL NO.': ['SN123456', 'CH789012'],
        'CONDITION': ['Good', 'Excellent'],
        'Purchase Date': ['2024-01-01', '2024-01-15'],
        'Depreciation Start Date': ['2024-01-01', '2024-01-15'],
        'Useful life (Yrs)': [3, 5],
        'DISPOSAL Date': ['', ''],
        'INITIAL COST': [1200.00, 350.00],
        'OTHER COST': [50.00, 0.00],
        'Entity': ['IT Department', 'Facilities'],
        'Currency': ['USD', 'USD']
    }

    df = pd.DataFrame(template_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Asset Template', index=False)

        instructions_df = pd.DataFrame({
            'Instructions': [
                'HOW TO USE THIS TEMPLATE:',
                '1. Do not modify the column headers',
                '2. Fill in your asset data starting from row 2',
                '3. Date format must be YYYY-MM-DD (e.g., 2024-01-01)',
                '4. Leave DISPOSAL Date empty if asset is still active',
                '5. ASSET CATEGORY examples: Electronics, Furniture, Vehicles, Machinery, etc.',
                '6. Required fields: ASSET NO., ASSET CATEGORY, DESCRIPTION, USER, CONDITION,',
                '   Purchase Date, Depreciation Start Date, Useful life (Yrs), INITIAL COST, Entity, Currency',
                '7. Save the file and use the Import from Excel button to upload'
            ]
        })
        instructions_df.to_excel(writer, sheet_name='Instructions', index=False)

    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='asset_register_template.xlsx'
    )

@app.route('/import/excel', methods=['POST'])
def import_excel():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Please upload an Excel file (.xlsx or .xls)'}), 400

        try:
            df = pd.read_excel(file, engine='openpyxl')
        except Exception as e1:
            try:
                file.seek(0)
                df = pd.read_excel(file)
            except Exception as e2:
                return jsonify({'success': False, 'error': f'Error reading Excel file: {str(e2)}'}), 400

        if df.empty:
            return jsonify({'success': False, 'error': 'The Excel file is empty'}), 400

        df.columns = df.columns.str.strip()

        required_columns = ['ASSET NO.', 'DESCRIPTION', 'USER', 'CONDITION', 'Purchase Date',
                            'Depreciation Start Date', 'Useful life (Yrs)', 'INITIAL COST', 'Entity', 'Currency']

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({'success': False, 'error': f'Missing required columns: {", ".join(missing_columns)}'}), 400

        imported_count = 0
        skipped_count = 0
        errors = []

        for index, row in df.iterrows():
            try:
                if pd.isna(row.get('ASSET NO.')) or str(row.get('ASSET NO.')).strip() == '':
                    skipped_count += 1
                    continue

                asset_no = str(row['ASSET NO.']).strip()
                existing = Asset.query.filter_by(asset_no=asset_no).first()
                if existing:
                    errors.append(f"Row {index + 2}: Asset No. {asset_no} already exists")
                    skipped_count += 1
                    continue

                category = 'Uncategorized'
                if 'ASSET CATEGORY' in df.columns and pd.notna(row.get('ASSET CATEGORY')):
                    category = str(row['ASSET CATEGORY']).strip()
                    existing_category = Category.query.filter_by(name=category).first()
                    if not existing_category and category != 'Uncategorized':
                        new_category = Category(name=category, created_date=datetime.now().date())
                        db.session.add(new_category)

                try:
                    purchase_date = pd.to_datetime(row['Purchase Date']).date()
                except:
                    errors.append(f"Row {index + 2}: Invalid Purchase Date format")
                    skipped_count += 1
                    continue

                try:
                    depreciation_start_date = pd.to_datetime(row['Depreciation Start Date']).date()
                except:
                    errors.append(f"Row {index + 2}: Invalid Depreciation Start Date format")
                    skipped_count += 1
                    continue

                disposal_date = None
                if 'DISPOSAL Date' in df.columns and pd.notna(row.get('DISPOSAL Date')) and str(
                        row.get('DISPOSAL Date')).strip():
                    try:
                        disposal_date = pd.to_datetime(row['DISPOSAL Date']).date()
                    except:
                        errors.append(f"Row {index + 2}: Invalid Disposal Date format")
                        skipped_count += 1
                        continue

                other_cost = 0
                if 'OTHER COST' in df.columns and pd.notna(row.get('OTHER COST')):
                    try:
                        other_cost = float(row['OTHER COST'])
                    except:
                        other_cost = 0

                try:
                    useful_life = float(row['Useful life (Yrs)'])
                except:
                    errors.append(f"Row {index + 2}: Invalid Useful life value")
                    skipped_count += 1
                    continue

                try:
                    initial_cost = float(row['INITIAL COST'])
                except:
                    errors.append(f"Row {index + 2}: Invalid INITIAL COST value")
                    skipped_count += 1
                    continue

                asset = Asset(
                    asset_no=asset_no,
                    asset_category=category,
                    description=str(row['DESCRIPTION']).strip(),
                    user=str(row['USER']).strip(),
                    serial_no=str(row.get('SERIAL NO.', '')).strip() if 'SERIAL NO.' in df.columns and pd.notna(
                        row.get('SERIAL NO.')) else '',
                    condition=str(row['CONDITION']).strip(),
                    purchase_date=purchase_date,
                    depreciation_start_date=depreciation_start_date,
                    useful_life_yrs=useful_life,
                    disposal_date=disposal_date,
                    initial_cost=initial_cost,
                    other_cost=other_cost,
                    entity=str(row['Entity']).strip(),
                    currency=str(row['Currency']).strip() if 'Currency' in df.columns else 'USD'
                )
                db.session.add(asset)
                imported_count += 1

            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")
                skipped_count += 1
                continue

        db.session.commit()

        message = f'Successfully imported {imported_count} assets'
        if skipped_count > 0:
            message += f', skipped {skipped_count} rows'
        if errors:
            message += f'. First few errors: {"; ".join(errors[:3])}'

        return jsonify({'success': True, 'message': message, 'imported': imported_count, 'skipped': skipped_count,
                        'errors': errors[:5]})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== DEPRECIATION SCHEDULE ROUTES ====================

@app.route('/depreciation/schedule')
def depreciation_schedule():
    assets = Asset.query.all()
    schedules = [calculate_asset_depreciation(asset) for asset in assets]
    return render_template('depreciation_schedule.html', schedules=schedules)

@app.route('/depreciation/schedule/<int:asset_id>')
def asset_depreciation_schedule(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    schedule = calculate_asset_depreciation(asset)
    return render_template('asset_depreciation.html', schedule=schedule)

@app.route('/depreciation/export/excel')
def export_depreciation_excel():
    assets = Asset.query.all()
    all_schedules = []

    for asset in assets:
        schedule = calculate_asset_depreciation(asset)
        for breakdown in schedule['yearly_breakdown']:
            all_schedules.append({
                'Asset No': breakdown['asset_no'],
                'Description': breakdown['description'],
                'Year': breakdown['year'],
                'Year Start': breakdown['year_start'],
                'Year End': breakdown['year_end'],
                'Depreciation': breakdown['depreciation'],
                'Accumulated Depreciation': breakdown['accumulated_depreciation'],
                'Net Book Value': breakdown['net_book_value']
            })

    df = pd.DataFrame(all_schedules)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Depreciation Schedule', index=False)

        worksheet = writer.sheets['Depreciation Schedule']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 25)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'depreciation_schedule_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/report/html')
def generate_html_report():
    assets = Asset.query.all()
    assets_data = [asset.to_dict() for asset in assets]

    total_cost = sum(a['initial_cost'] + a['other_cost'] for a in assets_data)
    active_assets = len([a for a in assets_data if not a['disposal_date']])
    disposed_assets = len([a for a in assets_data if a['disposal_date']])

    categories = {}
    for asset in assets_data:
        category = asset.get('asset_category', 'Uncategorized')
        if category not in categories:
            categories[category] = {'count': 0, 'total_cost': 0}
        categories[category]['count'] += 1
        categories[category]['total_cost'] += asset['initial_cost'] + asset['other_cost']

    return render_template('pdf_report.html',
                           assets=assets_data,
                           total_cost=total_cost,
                           active_assets=active_assets,
                           disposed_assets=disposed_assets,
                           categories=categories,
                           generated_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

# ==================== PERIOD DEPRECIATION REPORT ====================

@app.route('/api/categories')
def get_categories():
    categories = Category.query.order_by(Category.name).all()
    return jsonify({'categories': [c.name for c in categories]})

@app.route('/api/categories/all')
def get_all_categories():
    categories = Category.query.order_by(Category.name).all()
    return jsonify({'categories': [c.to_dict() for c in categories]})

@app.route('/api/categories', methods=['POST'])
def add_category():
    try:
        data = request.json
        category_name = data.get('category', '').strip()

        if not category_name:
            return jsonify({'success': False, 'error': 'Category name is required'}), 400

        existing = Category.query.filter_by(name=category_name).first()
        if existing:
            return jsonify({'success': False, 'error': 'Category already exists'}), 400

        new_category = Category(name=category_name, created_date=datetime.now().date())
        db.session.add(new_category)
        db.session.commit()

        return jsonify({'success': True, 'message': f'Category "{category_name}" created successfully',
                        'category': new_category.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/categories/<category_name>', methods=['DELETE'])
def delete_category(category_name):
    try:
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            return jsonify({'success': False, 'error': 'Category not found'}), 404

        assets = Asset.query.filter_by(asset_category=category_name).all()
        for asset in assets:
            asset.asset_category = 'Uncategorized'

        db.session.delete(category)
        db.session.commit()

        return jsonify({'success': True,
                        'message': f'Category "{category_name}" deleted. {len(assets)} assets reassigned to "Uncategorized".'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== CATEGORY DEPRECIATION SUMMARY ====================


@app.route('/reports/asset-movement')
def asset_movement_report():
    """Show fixed asset movement report for a selected period with entity filter"""
    # Get distinct entities for filter dropdown
    entities = db.session.query(Asset.entity).distinct().all()
    entities = [e[0] for e in entities if e[0]]

    # Get categories for filter dropdown
    categories = [c.name for c in Category.query.order_by(Category.name).all() if c.name != 'Uncategorized']

    return render_template('asset_movement_report.html',
                           entities=entities,
                           categories=categories)


@app.route('/api/reports/asset-movement', methods=['POST'])
def api_asset_movement_report():
    try:
        data = request.json
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        entity = data.get('entity', '')
        category = data.get('category', '')

        query = Asset.query
        if entity and entity != 'all':
            query = query.filter(Asset.entity == entity)
        if category and category != 'all':
            query = query.filter(Asset.asset_category == category)

        assets = query.all()
        categories_data = {}

        for asset in assets:
            asset_category = asset.asset_category if asset.asset_category else 'Uncategorized'
            movement_data = calculate_asset_movement(asset, start_date, end_date)

            if asset_category not in categories_data:
                categories_data[asset_category] = {
                    'category': asset_category,
                    'assets': [],
                    'totals': {
                        'cost_opening': 0, 'cost_additions': 0, 'cost_disposals': 0, 'cost_closing': 0,
                        'depn_opening': 0, 'depn_period': 0, 'depn_disposals': 0, 'depn_closing': 0,
                        'nbv_opening': 0, 'nbv_closing': 0
                    }
                }

            categories_data[asset_category]['assets'].append(movement_data)
            cat_totals = categories_data[asset_category]['totals']
            cat_totals['cost_opening'] += movement_data['cost_opening']
            cat_totals['cost_additions'] += movement_data['cost_additions']
            cat_totals['cost_disposals'] += movement_data['cost_disposals']
            cat_totals['cost_closing'] += movement_data['cost_closing']
            cat_totals['depn_opening'] += movement_data['depn_opening']
            cat_totals['depn_period'] += movement_data['depn_period']
            cat_totals['depn_disposals'] += movement_data['depn_disposals']
            cat_totals['depn_closing'] += movement_data['depn_closing']
            cat_totals['nbv_opening'] += movement_data['nbv_opening']
            cat_totals['nbv_closing'] += movement_data['nbv_closing']

        grand_totals = {
            'cost_opening': 0, 'cost_additions': 0, 'cost_disposals': 0, 'cost_closing': 0,
            'depn_opening': 0, 'depn_period': 0, 'depn_disposals': 0, 'depn_closing': 0,
            'nbv_opening': 0, 'nbv_closing': 0
        }

        for cat_data in categories_data.values():
            for key in grand_totals:
                grand_totals[key] += cat_data['totals'][key]

        return jsonify({
            'success': True,
            'categories': list(categories_data.values()),
            'grand_totals': grand_totals,
            'filters': {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'entity': entity if entity != 'all' else 'All Entities',
                'category': category if category != 'all' else 'All Categories'
            },
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/reports/asset-movement/export/excel', methods=['POST'])
def export_asset_movement_excel():
    try:
        data = request.json
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        entity = data.get('entity', '')
        category = data.get('category', '')

        query = Asset.query
        if entity and entity != 'all':
            query = query.filter(Asset.entity == entity)
        if category and category != 'all':
            query = query.filter(Asset.asset_category == category)

        assets = query.all()

        excel_data = []
        for asset in assets:
            movement = calculate_asset_movement(asset, start_date, end_date)
            excel_data.append({
                'Category': asset.asset_category if asset.asset_category else 'Uncategorized',
                'Asset No': movement['asset_no'],
                'Description': movement['description'],
                'User': movement['user'],
                'Entity': movement['entity'],
                'Cost - Opening': movement['cost_opening'],
                'Cost - Additions': movement['cost_additions'],
                'Cost - Disposals': movement['cost_disposals'],
                'Cost - Closing': movement['cost_closing'],
                'Acc Depn - Opening': movement['depn_opening'],
                'Acc Depn - Period': movement['depn_period'],
                'Acc Depn - Disposals': movement['depn_disposals'],
                'Acc Depn - Closing': movement['depn_closing'],
                'Net Book Value - Opening': movement['nbv_opening'],
                'Net Book Value - Closing': movement['nbv_closing']
            })

        df = pd.DataFrame(excel_data)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Asset Movement', index=False)

            for sheetname in writer.sheets:
                worksheet = writer.sheets[sheetname]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 30)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'asset_movement_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    print("=" * 60)
    print("ASSET REGISTER MANAGEMENT SYSTEM")
    print("=" * 60)
    print("✓ Flask Application Started")
    print("✓ Database initialized: assets.db")
    print("✓ Category Management System Active")
    print("✓ Depreciation Schedule routes added")
    print("✓ Asset Movement Report FIXED - Partial months now work correctly")
    print("✓ Pandas version:", pd.__version__)
    print("\n🌐 Access the application at: http://localhost:5000")
    print("\n📊 Available Routes:")
    print("   - /                        : Main Asset Register")
    print("   - /categories              : Category Management")
    print("   - /depreciation/schedule   : Depreciation Schedule")
    print("   - /depreciation/report     : Period Depreciation Report")
    print("   - /reports/asset-movement  : Asset Movement Report")
    print("   - /report/html             : HTML Report")
    print("=" * 60)
    app.run(debug=True, port=5000)