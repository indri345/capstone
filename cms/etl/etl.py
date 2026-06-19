import pandas as pd
from django.db import connection
from django.utils.timezone import now


# =====================================
# EXTRACT
# =====================================

def extract_event_data():

    query = """

        SELECT
            id,
            event_name,
            rating,
            views,
            engagement_score,
            created_at
        FROM cms_event

    """

    df = pd.read_sql(
        query,
        connection
    )

    return df


# =====================================
# TRANSFORM
# =====================================

def calculate_recency(created_at):

    days = (
        now().date()
        - created_at.date()
    ).days

    if days <= 7:
        return 10

    elif days <= 30:
        return 7

    elif days <= 90:
        return 5

    return 2


def transform_event_data(df):

    df['recency_score'] = df[
        'created_at'
    ].apply(calculate_recency)

    df['recommendation_score'] = (

        (df['rating'] * 0.4)

        +

        (df['engagement_score'] * 0.3)

        +

        (df['recency_score'] * 0.3)

    )

    return df


# =====================================
# LOAD
# =====================================

def load_result(df):

    df = df.sort_values(
        by='recommendation_score',
        ascending=False
    )

    df.to_csv(

        'event_recommendation.csv',

        index=False
    )

    return df


# =====================================
# ETL PIPELINE
# =====================================

def run_etl():

    print("EXTRACTING DATA...")

    df = extract_event_data()

    print("TRANSFORMING DATA...")

    df = transform_event_data(df)

    print("LOADING RESULT...")

    result = load_result(df)

    print("ETL SUCCESS")

    return result