#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# vim: tabstop=2 shiftwidth=2 softtabstop=2 expandtab

import sys
import os
import datetime
import time
import random

import boto3

random.seed(47)

DRY_RUN = (os.getenv('DRY_RUN', 'false').lower() == 'true')
AWS_REGION = os.getenv('REGION_NAME', 'us-east-1')

OLD_DATABASE = os.getenv('OLD_DATABASE')
OLD_TABLE_NAME = os.getenv('OLD_TABLE_NAME')
NEW_DATABASE = os.getenv('NEW_DATABASE')
NEW_TABLE_NAME = os.getenv('NEW_TABLE_NAME')
WORK_GROUP = os.getenv('WORK_GROUP', 'primary')
OUTPUT_PREFIX = os.getenv('OUTPUT_PREFIX')
STAGING_OUTPUT_PREFIX = os.getenv('STAGING_OUTPUT_PREFIX')
COLUMN_NAMES = os.getenv('COLUMN_NAMES', '*')

EXTERNAL_LOCATION_FMT = '''{output_prefix}/year={year}/month={month:02}/day={day:02}/hour={hour:02}/'''

CTAS_QUERY_FMT = '''CREATE TABLE {new_database}.tmp_{new_table_name}
WITH (
  external_location='{location}',
  format = 'PARQUET',
  parquet_compression = 'SNAPPY')
AS SELECT {columns}
FROM {old_database}.{old_table_name}
WHERE year={year} AND month={month} AND day={day} AND hour={hour}
WITH DATA
'''

def run_drop_tmp_table(athena_client, basic_dt):
  year, month, day, hour = (basic_dt.year, basic_dt.month, basic_dt.day, basic_dt.hour)

  tmp_table_name = '{table}_{year}{month:02}{day:02}{hour:02}'.format(table=NEW_TABLE_NAME,
      year=year, month=month, day=day, hour=hour)

  output_location = '{}/tmp_{}'.format(STAGING_OUTPUT_PREFIX, tmp_table_name)
  query = 'DROP TABLE IF EXISTS {database}.tmp_{table_name}'.format(database=NEW_DATABASE,
      table_name=tmp_table_name)

  print('[INFO] QueryString:\n{}'.format(query), file=sys.stderr)
  print('[INFO] OutputLocation: {}'.format(output_location), file=sys.stderr)

  if DRY_RUN:
    print('[INFO] End of dry-run', file=sys.stderr)
    return

  response = athena_client.start_query_execution(
    QueryString=query,
    ResultConfiguration={
      'OutputLocation': output_location
    },
    WorkGroup=WORK_GROUP
  )
  print('[INFO] QueryExecutionId: {}'.format(response['QueryExecutionId']), file=sys.stderr)


def run_ctas(athena_client, basic_dt):
  year, month, day, hour = (basic_dt.year, basic_dt.month, basic_dt.day, basic_dt.hour)

  new_table_name = '{table}_{year}{month:02}{day:02}{hour:02}'.format(table=NEW_TABLE_NAME,
    year=year, month=month, day=day, hour=hour)

  output_location = '{}/tmp_{}'.format(STAGING_OUTPUT_PREFIX, new_table_name)
  external_location = EXTERNAL_LOCATION_FMT.format(output_prefix=OUTPUT_PREFIX,
    year=year, month=month, day=day, hour=hour)

  query = CTAS_QUERY_FMT.format(new_database=NEW_DATABASE, new_table_name=new_table_name,
    old_database=OLD_DATABASE, old_table_name=OLD_TABLE_NAME, columns=COLUMN_NAMES,
    year=year, month=month, day=day, hour=hour, location=external_location)

  print('[INFO] QueryString:\n{}'.format(query), file=sys.stderr)
  print('[INFO] ExternalLocation: {}'.format(external_location), file=sys.stderr)
  print('[INFO] OutputLocation: {}'.format(output_location), file=sys.stderr)

  if DRY_RUN:
    print('[INFO] End of dry-run', file=sys.stderr)
    return

  response = athena_client.start_query_execution(
    QueryString=query,
    QueryExecutionContext={
      'Database': NEW_DATABASE
    },
    ResultConfiguration={
      'OutputLocation': output_location
    },
    WorkGroup=WORK_GROUP
  )
  print('[INFO] QueryExecutionId: {}'.format(response['QueryExecutionId']), file=sys.stderr)


def lambda_handler(event, context):
  event_dt = datetime.datetime.strptime(event['time'], "%Y-%m-%dT%H:%M:%SZ")
  prev_basic_dt, basic_dt = [event_dt - datetime.timedelta(hours=e) for e in (2, 1)]

  client = boto3.client('athena')
  run_drop_tmp_table(client, prev_basic_dt)

  print('[INFO] Wait for a few seconds until dropping old table', file=sys.stderr)
  time.sleep(10)

  run_ctas(client, basic_dt)


if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument('-dt', '--basic-datetime', default=datetime.datetime.today().strftime('%Y-%m-%dT%H:05:00Z'),
    help='The scheduled event occurrence time ex) 2020-02-28T03:05:00Z')

  options = parser.parse_args()

  event = {
    "id": "cdc73f9d-aea9-11e3-9d5a-835b769c0d9c",
    "detail-type": "Scheduled Event",
    "source": "aws.events",
    "account": "{{{account-id}}}",
    "time": options.basic_datetime,
    "region": "us-east-1",
    "resources": [
      "arn:aws:events:us-east-1:123456789012:rule/ExampleRule"
    ],
    "detail": {}
  }
  print('[DEBUG] event:\n{}'.format(event), file=sys.stderr)
  lambda_handler(event, {})
