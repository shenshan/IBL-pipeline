import datajoint as dj
from ibl_pipeline.ingest import alyxraw, data, InsertBuffer
from ibl_pipeline.ingest import subject, action, acquisition, ephys
import json
import logging
import math
import collections
import os.path as path
import sys
import uuid
import re
from tqdm import tqdm

logger = logging.getLogger(__name__)
dir_name = path.dirname(__file__)

dj.config['safemode'] = False


print('Deleting experiments.channel...')
(alyxraw.AlyxRaw & 'model="experiments.channel"').delete()

filename = path.join(dir_name, '..', 'data', 'alyxfull.json')

with open(filename, 'r') as fid:
    keys_all = json.load(fid)

# remove invalid uuid from some tables
keys = [key for key in keys_all
        if key['model'] == 'experiments.channel']

# use insert buffer to speed up the insertion process
ib_main = InsertBuffer(alyxraw.AlyxRaw)
ib_part = InsertBuffer(alyxraw.AlyxRaw.Field)

# insert into AlyxRaw table
for key in tqdm(keys):
    try:
        pk = uuid.UUID(key['pk'])
    except Exception:
        print('Error for key: {}'.format(key))
        continue

    ib_main.insert1(dict(uuid=pk, model=key['model']))
    if ib_main.flush(skip_duplicates=True, chunksz=10000):
        logger.debug('Inserted 10000 raw tuples.')
        # print('Inserted 10000 raw tuples.')

if ib_main.flush(skip_duplicates=True):
    logger.debug('Inserted remaining raw tuples')
    # print('Inserted remaining raw tuples')


# insert into the part table AlyxRaw.Field
for ikey, key in tqdm(enumerate(keys)):
    try:
        try:
            pk = uuid.UUID(key['pk'])
        except ValueError:
            print('Error for key: {}'.format(key))
            continue

        key_field = dict(uuid=uuid.UUID(key['pk']))
        for field_name, field_value in key['fields'].items():
            key_field = dict(key_field, fname=field_name)

            if field_name == 'json' and field_value is not None:

                key_field['value_idx'] = 0
                key_field['fvalue'] = json.dumps(field_value)
                if len(key_field['fvalue']) < 10000:
                    ib_part.insert1(key_field)
                else:
                    continue
            if field_name == 'narrative' and field_value is not None:
                # filter out emoji
                emoji_pattern = re.compile(
                    "["
                    u"\U0001F600-\U0001F64F"  # emoticons
                    u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                    u"\U0001F680-\U0001F6FF"  # transport & map symbols
                    u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                    u"\U00002702-\U000027B0"
                    u"\U000024C2-\U0001F251"
                    "]+", flags=re.UNICODE)

                key_field['value_idx'] = 0
                key_field['fvalue'] = emoji_pattern.sub(r'', field_value)

            elif field_value is None or field_value == '' or field_value == [] or \
                    (isinstance(field_value, float) and math.isnan(field_value)):
                key_field['value_idx'] = 0
                key_field['fvalue'] = 'None'
                ib_part.insert1(key_field)

            elif type(field_value) is list and \
                    (type(field_value[0]) is dict or type(field_value[0]) is str):
                for value_idx, value in enumerate(field_value):
                    key_field['value_idx'] = value_idx
                    key_field['fvalue'] = str(value)
                    ib_part.insert1(key_field)
            else:
                key_field['value_idx'] = 0
                key_field['fvalue'] = str(field_value)
                ib_part.insert1(key_field)

            if ib_part.flush(skip_duplicates=True, chunksz=10000):
                logger.debug('Inserted 10000 raw field tuples')
                # print('Inserted 10000 raw field tuples')
    except Exception as e:
        print('Problematic entry:{}'.format(ikey))
        raise

if ib_part.flush(skip_duplicates=True):
    logger.debug('Inserted all remaining raw field tuples')