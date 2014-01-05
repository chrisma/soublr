#!/usr/bin/env python
"""
soublr. Import soup.io posts to Tumblr.

Usage:
  soublr.py <soup_export.rss> <tumblr_credentials.json>
  soublr.py -h | --help
  soublr.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
"""

import sys, json, atexit
import pytumblr
from lxml import etree
from docopt import docopt

processed = dict()
def _load_log():
	"""
	Load (global) list of already processed posts.
	Prompt to continue if log was not found. 
	"""
	# Read previous log file and prompt
	global processed
	try:
		processed = json.load(open(log_path, 'r'))
	except IOError, e:
		print 'No previous posts found in %s.' % log_path
		if raw_input('All items will be posted! Continue? [y/N] ') not in ('y','Y','yes'):
			sys.exit("Aborted.")

def parse_soup_rss(soup_rss):
	try:
		tree = etree.parse(soup_rss)
	except IOError, e:
		print e
		sys.exit(2) # command line error

	types = dict()

	items = tree.findall('.//item')
	# Post oldest posts (at the bottom) first
	items.reverse()
	print "%s items found in soup rss." % len(items)
	return items

def _clean(dictionary):
	"""
	Return a dict with all keys removed whose values are None
	and all unicode strings encoded with utf-8.
	"""
	d = {k:v for k,v in dictionary.items() if v is not None}
	d = {k:v.encode('utf-8') if isinstance(v,unicode) else v for (k, v) in d.items()}
	return d

def _strip_html(string):
	try:
		if string:
			string = etree.fromstring(string).text
	except etree.XMLSyntaxError:
		pass #if XML was malformed, leave it as it is
	return string

@atexit.register
def _dump_log():
	"""
	Dump log in json format.
	"""
	try:
		json.dump(processed, open(log_path, 'w'), indent=2, sort_keys=True)
		print 'Logged posts to %s' % log_path
	except IOError, e:
		print 'WARNING: Could not write log!'
		sys.exit(e)

def post_to_tumblr(posts, client, footer=''):
	global processed
	_load_log() # populate processed
	count_before = len(processed)
	blog_name = client.info()['user']['blogs'][0]['url'].lstrip('http://').rstrip('/')
	
	count = 0
	for post in posts:
		# Skip already processed posts
		post_guid = post.find('guid').text
		if post_guid in processed.keys():
			print "Skipping %s, already at %s" % (post_guid, processed[post_guid])
			continue

		# Parse JSON-encoded soup.io attributes element
		attribs_element = post.find('{http://www.soup.io/rss}attributes')
		attribs = json.loads(attribs_element.text)
		# Load None as empty string, loads doesn't support parse_constant for 'null' anymore since 2.7
		attribs = {k:u'' if v is None else v for (k,v) in attribs.items()}

		soup_link = post.find('link').text
		post_footer = footer.format(soup_link=soup_link)
		response = None
		
		args = dict()
		# All post types (http://www.tumblr.com/docs/en/api/v2#ppt-all)
		args['date'] = post.find('pubDate').text
		args['tags'] = attribs['tags'] + [u'soup.io']
		slug = post.find('title').text
		args['slug'] = slug.encode('ascii', 'ignore') if slug else None
		#{u'link': 37, u'image': 1715, u'regular': 62, u'video': 360, u'quote': 86}
		post_type = attribs['type']
		if post_type == 'image':
			# Photo posts (http://www.tumblr.com/docs/en/api/v2#pphoto-posts)
			args['caption'] = attribs['body'] + post_footer
			args['link'] = attribs['source']
			args['source'] = attribs['url']
			response = client.create_photo(blog_name, **_clean(args))
		elif post_type == 'video':
			# Video posts (http://www.tumblr.com/docs/en/api/v2#pvideo-posts)
			args['caption'] = attribs['body'] + post_footer
			args['embed'] = attribs['embedcode_or_url']
			response = client.create_video(blog_name, **_clean(args))
		elif post_type == 'regular':
			# Text posts (http://www.tumblr.com/docs/en/api/v2#ptext-posts)
			args['title'] = _strip_html(attribs['title'])
			args['body'] = attribs['body'] + post_footer
			response = client.create_text(blog_name, **_clean(args))
		elif post_type == 'link':
			# Link posts (http://www.tumblr.com/docs/en/api/v2#plink-posts)
			args['title'] = attribs['title']
			args['url'] = attribs['source']
			args['description'] = attribs['body'] + post_footer
			response = client.create_link(blog_name, **_clean(args))
		elif post_type == 'quote':
			# Quote posts (http://www.tumblr.com/docs/en/api/v2#pquote-posts)
			args['quote'] = attribs['body']
			args['source'] = attribs['title'] + post_footer
			response = client.create_quote(blog_name, **_clean(args))
		else:
			print "WARNING: Post type '%s' not supported. Skipping."
			continue

		# Check if request was successful
		try:
			tumblr_id = response['id']
		except (KeyError, TypeError):
			# Error when posting
			print "Posting of '%s' (%s) failed.\n%s" % (args['slug'], post_guid, response)
			continue # Skip this post
		# Success
		count += 1
		print "'%s' posted to %s/post/%s" % (args['slug'], blog_name, tumblr_id)

		# Keep log of already posted items for future runs
		processed[post_guid] = '%s/post/%d' % (blog_name, tumblr_id)

	print '%s posts submitted this run. %s total (%s before)' % (count, count+count_before, count_before)
	sys.exit() # _dump_log() runs

def setup_pytumblr(credentials_path):
	credentials = json.load(open(credentials_path, 'r'))
	client = pytumblr.TumblrRestClient(**credentials)
	print "Using blog", client.info()['user']['blogs'][0]['url']
	return client

def soublr(rss, cred_path, footer):
	posts = parse_soup_rss(soup_rss)
	client = setup_pytumblr(credentials_path)
	post_to_tumblr(posts, client, footer)


if __name__ == '__main__':
	arguments = docopt(__doc__, version='0.1')
	
	soup_rss = arguments.get('<soup_export.rss>')
	credentials_path = arguments.get('<tumblr_credentials.json>')
	footer = '<p><font color="#757575">(Imported from <a href="{soup_link}">soup.io</a>)</font></p>'.encode('utf-8')
	
	# Global
	log_path = sys.argv[0].replace('py','log') # Name of .py file with .log extensions
	
	soublr(soup_rss, credentials_path, footer)
