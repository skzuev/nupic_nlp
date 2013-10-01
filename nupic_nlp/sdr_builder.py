import os
import sys
import json
from text_reader import Noun_Reader
import pycept


def plural(word):
  if word.endswith('y'):
    return word[:-1] + 'ies'
  elif word[-1] in 'sx' or word[-2:] in ['sh', 'ch']:
    return word + 'es'
  elif word.endswith('an'):
    return word[:-2] + 'en'
  else:
    return word + 's'


def write_sdr_cache(cache, path):
  with open(path, 'w') as f:
    f.write(json.dumps(cache))


def is_valid(sdr, min_sparcity):
  return sdr['sparcity'] > min_sparcity


def get_sdr(term, cept_client, cache_dir):
  # Create a cache location for each term, where it will either be read in from
  # or cached within if we have to go to the CEPT API to get the SDR.
  cache_file = os.path.join(cache_dir, term + '.json')
  # Get it from the cache if it's there.
  if os.path.exists(cache_file):
    cached_sdr = json.loads(open(cache_file).read())
  # Get it from CEPT API if it's not cached.
  else:
    print '\tfetching %s from CEPT API' % term
    cached_sdr = cept_client.getBitmap(term)
    if 'sparcity' not in cached_sdr:
      # attach the sparcity for reference
      total = float(cached_sdr['width']) * float(cached_sdr['height'])
      on = len(cached_sdr['positions'])
      sparcity = round((on / total) * 100)
      cached_sdr['sparcity'] = sparcity
    # write to cache
    with open(cache_file, 'w') as f:
      f.write(json.dumps(cached_sdr))
  return cached_sdr



class Builder(object):

  def __init__(self, cept_app_id, cept_app_key, cache_dir):
    self.cept_client = pycept.Cept(cept_app_id, cept_app_key)
    self.cache_dir = cache_dir
    self.noun_reader = Noun_Reader(cache_dir)


  def build_nouns(self, max_terms, min_sparcity):
    
    cept_client = self.cept_client
    cache_dir = self.cache_dir

    if max_terms > 10:
      progress_at = int(max_terms / 10)
    else:
      progress_at = 1

    # Create the cache directory if necessary.
    if not os.path.exists(cache_dir):
      os.mkdir(cache_dir)

    all_nouns = self.noun_reader.get_nouns_from_all_texts()

    # We're only processing the least amount of terms, either of the total number
    # of nouns available, or the number the user specified.
    max_terms = min(len(all_nouns), max_terms)

    print 'processing %i nouns...' % max_terms

    # Convert nouns into pairs of singular / plural nouns.
    term_pair = [ (n, plural(n)) for n in all_nouns ]

    # Some won't be adequate, so we'll only keep the good ones.
    valid_nouns = []
    # Just to track how many we've processed.
    terms_processed = 0
    terms_skipped = []

    for item in term_pair:
      # Singular term.
      sterm = item[0]
      # Plural term.
      pterm = item[1]
      # sys.stdout.write('%s, ' % (sterm,))
      sbm = get_sdr(sterm, cept_client, cache_dir)
      pbm = get_sdr(pterm, cept_client, cache_dir)

      # Only gather the ones we deem as 'valid'.
      if is_valid(sbm, min_sparcity) and is_valid(pbm, min_sparcity):
        valid_nouns.append({'term': sterm, 'bitmap': sbm})
        valid_nouns.append({'term': pterm, 'bitmap': pbm})
        terms_processed += 1
      else:
        # print '\tsdrs for %s and %s are too sparce, skipping!' % item
        terms_skipped.append(sterm)

      count = terms_processed + len(terms_skipped)
      if count >= max_terms:
        break

      # Print progress
      if count % progress_at == 0:
        print '\n%.0f%% done...' % (float(count) / float(max_terms) * 100)
        print '%i total terms reviewed, %i terms skipped' % (count, len(terms_skipped))

    skipped_out = os.path.join(cache_dir, 'skipped.txt')
    with open(skipped_out, 'w') as f:
      f.write(', '.join(terms_skipped))
    summary_out = os.path.join(cache_dir, 'summary.txt')
    with open(summary_out, 'w') as f:
      for n in valid_nouns:
        f.write("%20s: %.2f%%\n" % (n['term'], n['bitmap']['sparcity']))

    print '\nNoun extraction and conversion into SDRs is complete!'
    print '====================================================='
    print '* %i nouns and their plural forms were converted to SDRs within the %s directory' \
      % (len(valid_nouns)/2, cache_dir)
    print '\tSummary file written to %s' % summary_out
    print '* %i terms skipped because of %.1f%% sparcity requirement. These can be reviewed in %s' \
      % (len(terms_skipped), min_sparcity, skipped_out)

    return valid_nouns



  def convert_bitmap_to_sdr(self, bitmap):
    sdr_string = self.cept_client._bitmapToSdr(bitmap)
    return [int(bit) for bit in sdr_string]



  def closest_term(self, bitmap):
    closest = self.cept_client.bitmapToTerms(
      bitmap['width'], bitmap['height'], bitmap['positions'])
    if len(closest) is 0:
      return None
    else:
      return closest[0]['term']