from datamart.materializers.wikitables_materializer.utils import *

SELECTOR_ROOT = '#content table:not(.infobox):not(.navbox):not(.navbox-inner):not(.navbox-subgroup):not(.sistersitebox)'
FUNCTIONS = {-1: 'empty', 0: 'data', 1: 'header'}
PADDING_CELL = soup('<td data-padding-cell></td>', 'html.parser').td
FIND_DIGITS = compile(r"\d+").findall
FIND_STOPWORDS = lambda txt: [w for w in findall(r"[^\s]+", txt.lower()) if w in stopwords.words("english")]
COLOR_STYLE_PROPERTIES = ["color", "background-color", "border-left-color", "border-bottom-color", "border-right-color", "border-top-color", "outline-color"]
CATEGORICAL_STYLE_PROPERTIES = ["text-align", "font-family", "text-transform", "text-decoration", "vertical-align", "display", "tag"]
NUMERIC_STYLE_PROPERTIES = {"border-bottom-width": (-40, 40), "border-left-width": (-40, 40), "border-right-width": (-40, 40), "border-top-width": (-40, 40), "font-size": (0, 60), "padding-bottom": (-40, 40), "padding-left": (-40, 40), "padding-right": (-40, 40), "padding-top": (-40, 40), "font-weight": (400, 700)}
NUMERIC_STYLE_PROPERTIES = {k: (mn, mx - mn) for k, (mn, mx) in NUMERIC_STYLE_PROPERTIES.items()}
COMPUTED_STYLE_PROPERTIES = ["tag", "relative-width", "relative-height"]
DENSITY_SYNTAX_PROPERTIES = {"lowercase": r"\p{Ll}", "uppercase": r"\p{Lu}", "alphanumeric": r"\w", "digit": r"\d", "whitespace": r"\s", "symbol": r"[^\w\s]", "token": r"[^\s]+"}
DENSITY_SYNTAX_PROPERTIES = {k: compile(v).findall for k, v in DENSITY_SYNTAX_PROPERTIES.items()}
DENSITY_SYNTAX_PROPERTIES["stopwords"] = FIND_STOPWORDS
BOOLEAN_SYNTAX_PROPERTIES = {"capitalised": r"(\p{Lu}(\p{Ll}+|\.)\s)*\p{Lu}(\p{Ll}+|\.)", "allcaps": r"\p{Lu}+", "money": r"[\$£]\s*\d+([.,] ?\d+)?\s*$|\d+([.,] ?\d+)?\s*€", "amount": r"([\-\+]\s*)?[\d ,\.]+", "range": r"((\+\-)?\s*\d[\d(,\s?)\.]*[\-\–(to),\s]*)+", "empty": r""}
BOOLEAN_SYNTAX_PROPERTIES = {k: compile("^%s$" % v).match for k, v in BOOLEAN_SYNTAX_PROPERTIES.items()}
BOOLEAN_SYNTAX_PROPERTIES["date"] = find_dates

HTML_ARTICLE_TEMPLATE = '<!doctype html><html><head><meta charset="utf-8"><title>%s</title><link rel="stylesheet" href="style.css"><script src="script.js"></script></head><body><div id="popup"></div><h1><a href="%s" target="_blank">%s</a><time>Generated by %s</time></h1>%s</body></html>'
MAX_SPAN = 150
WIKIPEDIA_IGNORE_CATEGORIES = ['articles', 'cs1', 'page', 'dates', ' use']

def locate(url, document):
	res = []
	if document.select_one('.noarticletext') != None:
		log('info', f'Article {url} does not exist.')
	else:
		for table in document.select('table[data-xpath]'):
			child_tables = len(table.select('table'))
			rows = len(table.select('tr'))
			cols = len(table.select('td')) / rows if rows > 0 else 0
			if rows > 1 and cols > 1 and not child_tables:
				res.append(Table(url, table, table['data-xpath']))
	return res

def segmentate(table):
	elements = [[cell for cell in row.select('th,td')] for row in table.element.select('tr')]
	elements, contextual_info = clean_table(elements)
	features = []
	texts = []
	for row in elements:
		row_data = []
		row_text = []
		for cell in row:
			if 'data-padding-cell' in cell.attrs:
				cell_feats = dict()
			else:
				cell_feats = extract_features(cell)
				del cell_feats['width']
				del cell_feats['height']
			row_data.append(cell_feats)
			row_text.append(' '.join(t.strip() for t in cell.find_all(text=True)).strip())
		features.append(row_data)
		texts.append(row_text)
	table.features = features
	table.texts = texts
	table.contextual_info = contextual_info
	add_variability(table)

def clean_table(table):
	contextual_info = {}
	# convert colspans to int and avoid huge span
	for r, row in enumerate(table):
		for c, cell in enumerate(row):
			if 'colspan' in cell.attrs:
				try:
					cell['colspan'] = min(MAX_SPAN, int(cell['colspan']))
				except:
					cell['colspan'] = 1
			if 'rowspan' in cell.attrs:
				try:
					cell['rowspan'] = min(MAX_SPAN, int(cell['rowspan']))
				except:
					cell['rowspan'] = 1
	# split and copy colspan
	spanned_cells = []
	for r, row in enumerate(table):
		for c, cell in enumerate(row):
			if 'colspan' in cell.attrs and (r, c) not in spanned_cells:
				for n in range(cell['colspan'] - 1):
					table[r].insert(c, cell)
					spanned_cells.append((r, c + 1 + n))
	# split and copy rowspan
	spanned_cells = []
	for c in range(len(table[0])):
		for r in range(len(table)):
			if c < len(table[r]) and 'rowspan' in table[r][c].attrs and (r, c) not in spanned_cells:
				for n in range(1, min(len(table) - r, table[r][c]['rowspan'])):
					table[r + n].insert(c, table[r][c])
					spanned_cells.append((r + n, c))
	# pad with trailing cells
	width = max(len(row) for row in table)
	table = [row + [PADDING_CELL] * (width - len(row)) for row in table]
	# transform empty cells into padding cells
	for r, row in enumerate(table):
		for c, cell in enumerate(row):
			if not len(' '.join(t.strip() for t in cell.find_all(text=True)).strip()):
				table[r][c] = PADDING_CELL
	# remove non-data rows until no changes are applied to the table
	changed = True
	while changed:
		dims = [len(r) for r in table]
		# remove rows where every cell has rowspan > 1
		for r in reversed(range(len(table))):
			if all('rowspan' in cell.attrs and cell['rowspan'] > 1 or cell == PADDING_CELL for cell in table[r]):
				table = table[:r] + table[r + 1:]
		# remove cols where every cell has colspan > 1
		if len(table):
			for c in reversed(range(len(table[0]))):
				if all('colspan' in row[c].attrs and row[c]['colspan'] > 1 or row[c] == PADDING_CELL for row in table):
					table = [row[:c] + row[c + 1:] for row in table]
		# remove rows with full table colspan
		to_remove = [r for r, row in enumerate(table) if all(row[c - 1] == row[c] for c in range(1, len(row)))]
		contextual_info.update({r: table[r][0].text.strip() for r in to_remove})
		table = [row for r, row in enumerate(table) if r not in to_remove]
		# remove cols with full table rowspan
		if len(table):
			for c in reversed(range(len(table[0]))):
				if all(table[r - 1][c] == table[r][c] for r in range(1, len(table))):
					table = [row[:c] + row[c + 1:] for row in table]
		# remove repeated rows
		repeated_texts = [[c.text.strip() for c in row] for row in table]
		repeated_texts = [text in repeated_texts[:t] for t, text in enumerate(repeated_texts)]
		table = [row for row, repeated in zip(table, repeated_texts) if not repeated]
		# remove repeated columns
		if len(table):
			repeated_texts = [[row[c].text.strip() for row in table] for c in range(len(table[0]))]
			repeated_texts = [text in repeated_texts[:t] for t, text in enumerate(repeated_texts)]
			for c, repeated in enumerate(repeated_texts):
				if repeated:
					table = [row[:c] + row[c + 1:] for row in table]
		# remove empty rows
		table = [row for row in table if any(len(cell.text.strip()) for cell in row)]
		# remove empty columns
		cols_to_remove = []
		if len(table):
			for c in range(len(table[0])):
				if not any(len(table[r][c].text.strip()) for r in range(len(table))):
					cols_to_remove.append(c)
			for col in reversed(cols_to_remove):
				table = [row[:col] + row[col + 1:] for row in table]
		changed = dims != [len(r) for r in table]
	return table, contextual_info

def extract_features(element):
	if 'data-computed-style' not in element.attrs:
		return None
	css_properties = [prop.split(':') for prop in element['data-computed-style'].split('|')]
	css_properties = {k: v for k, v in css_properties}
	# compute style properties
	res = {}
	for p in COLOR_STYLE_PROPERTIES:
		val = css_properties[p]
		res[p + '-r'], res[p + '-g'], res[p + '-b'] = [float(c) / 255 for c in FIND_DIGITS(val)[:3]]
	for p in CATEGORICAL_STYLE_PROPERTIES:
		if p != 'tag':
			res[p] = css_properties[p]
	for p, (mn, wide) in NUMERIC_STYLE_PROPERTIES.items():
		val = css_properties[p]
		res[p] = max(0, min(1, (float(FIND_DIGITS(val)[0]) - mn) / wide))
	res['tag'] = element.name
	res['width'] = max(0, min(1, float(css_properties['width'])))
	res['height'] = max(0, min(1, float(css_properties['height'])))
	# compute syntax properties
	text = ' '.join(element.find_all(text=True, recursive=False)).strip()
	ln = len(text)
	for p, reg in DENSITY_SYNTAX_PROPERTIES.items():
		if ln:
			res[p] = len(reg(text)) / ln
		else:
			res[p] = 0
	for p, reg in BOOLEAN_SYNTAX_PROPERTIES.items():
		res[p] = 1 if reg(text) else 0
	# add children render info
	area = res['width'] * res['height']
	nodes = []
	for c in element.find_all(recursive=False):
		if len(c.text.strip()) and 'data-computed-style' in c.attrs:
			child = extract_features(c)
			if child == None:
				continue
			child_area = child['width'] * child['height']
			#area -= child_area
			nodes.append([child_area, child])
	nodes.insert(0, [area, res])
	res = vectors_weighted_average(nodes)
	res['tag'] = element.name
	res['children'] = max(0, min(1, len(element.find_all()) / 5))
	if res['tag'] in ['th', 'td']:
		res['colspan'] = int(css_properties['colspan'])
		res['rowspan'] = int(css_properties['rowspan'])
	return res

def add_variability(table):
	if len(table.features) == 0:
		table.variabilities = {'row': 0, 'col': 0, 'table': 0}
		return
	row_features = [vectors_average(row) for row in table.features]
	col_features = [vectors_average([row[col] for row in table.features]) for col in range(table.cols())]
	tab_features = vectors_average([cell for row in table.features for cell in row])

	total_row_variability = []
	total_col_variability = []
	total_table_variability = []

	for r, row in enumerate(table.features):
		for c, cell in enumerate(row):
			if len(cell) == 0: continue
			row_variabilities = vectors_difference(cell, row_features[r], prefix='row-variability-')
			col_variabilities = vectors_difference(cell, col_features[c], prefix='col-variability-')
			table_variabilities = vectors_difference(cell, tab_features, prefix='tab-variability-')
			table.features[r][c] = {**cell, **row_variabilities, **col_variabilities, **table_variabilities}
			total_row_variability.append(vector_module(row_variabilities))
			total_col_variability.append(vector_module(col_variabilities))
			total_table_variability.append(vector_module(table_variabilities))

	table.variabilities = {
		'row': sum(total_row_variability) / len(total_row_variability),
		'col': sum(total_col_variability) / len(total_col_variability),
		'table': sum(total_table_variability) / len(total_table_variability)
	}

def functional_analysis(table):
	features = binarize_categorical(table.features)
	cells = [sorted(c.items()) for row in features for c in row if len(c)]
	cells = [[f[1] for f in features] for features in cells]
	km = KMeans(n_clusters=2).fit(cells)
	functions = []
	n = 0
	for r in range(table.rows()):
		functions.append([])
		for c in range(table.cols()):
			if len(features[r][c]):
				functions[-1].append(km.labels_[n])
				n += 1
			else:
				functions[-1].append(-1)
	if table.rows() <= 2 or table.cols() <= 2:
		pos = [[], []]
		for r, row in enumerate(functions):
			for c, cell in enumerate(row):
				pos[cell].append((r, c))
		pos = [[sum([e[n] for e in elem]) / len(elem) for n in range(2)] for elem in pos]
		pos = [sqrt(x**2 + y**2) for x, y in pos]
		exchange = pos[1] > pos[0]
	else:
		values = [f for row in functions for f in row]
		exchange = values.count(0) < values.count(1)
	if exchange:
		exchange_dict = {-1: -1, 0: 1, 1: 0}
		functions = [[exchange_dict[c] for c in row] for row in functions]
	else:
		functions = [[int(c) for c in row] for row in functions]
	table.functions = functions
	with open(join(PATH_RESOURCES, 'debug.json'), 'w', encoding='utf-8') as fp:
		dump({'texts': table.texts, 'features': table.features, 'functions': table.functions}, fp)

def structural_analysis(table):
	rv, cv, tv = table.variabilities['row'], table.variabilities['col'], table.variabilities['table']
	all_headers = all(c == 1 for row in table.functions for c in row if c != -1)
	all_data = all(c == 0 for row in table.functions for c in row if c != -1)
	first_row_header = all(c == 1 for c in table.functions[0] if c != -1)
	first_col_header = all(row[0] == 1 for row in table.functions if row[0] != -1)
	if all_headers or all_data:
		min_variability = min(rv, cv, tv)
		if min_variability == rv:
			table.kind = 'horizontal listing'
			if all_headers:
				table.functions = [[1] * table.cols()] + [[0] * table.cols()] * (table.rows() - 1)
		elif min_variability == cv:
			table.kind = 'vertical listing'
			if all_headers:
				table.functions = [[[1] + [0] * table.cols()] for _ in range(table.rows())]
		else:
			table.kind = 'enumeration'
	elif first_row_header and first_col_header:
		table.kind = 'matrix'
	elif first_row_header:
		table.kind = 'horizontal listing'
	elif first_col_header:
		table.kind = 'vertical listing'

def interpret(table):
	# TODO: Implement, Hierarchical headers, split-repeated headers
	if table.kind == 'enumeration' or table.kind == 'unknown':
		res = [{'attribute_0': text} for row in table.texts for text in row if len(text)]
	elif table.kind == "matrix":
		res = [
			{'attribute_0': table.texts[r][0], 'attribute_1': table.texts[0][c], 'attribute_3': table.texts[r][c]}
			for r, row in enumerate(table.functions) for c, cell in enumerate(row) if cell == 0
		]
	elif table.kind == 'horizontal listing':
		res = [{k: v for k, v in zip(table.texts[0], row)} for row in table.texts[1:]]
	elif table.kind == 'vertical listing':
		first_column = [row[0] for row in table.texts]
		res = [{k: v for k, v in zip(first_column, [r[c] for r in table.texts])} for c in range(1, table.cols())]
	table.record = res

_compute_score_functions = {0: 1, -1: 0.5, 1: 0}
def compute_score(table):
	if table.kind == 'unknown':
		score = 0
	else:
		multiplier = 1
		data_area = table.functions
		max_var = max(table.variabilities.values())
		if table.kind == 'horizontal listing':
			data_area = data_area[1:]
			if max_var != table.variabilities['row']: multiplier *= .75
			digits = [cell['digit'] for cell in table.features[0] if 'digit' in cell]
			multiplier *= sum(1 for d in digits if d == 0) / len(digits)
		elif table.kind == 'vertical listing':
			data_area = [row[1:] for row in data_area]
			if max_var != table.variabilities['col']: multiplier *= .75
			digits = [row[0]['digit'] for row in table.features if 'digit' in row[0]]
			multiplier *= sum(1 for d in digits if d == 0) / len(digits)
		elif table.kind == 'matrix':
			data_area = [row[1:] for row in data_area[1:]]
			if max_var != table.variabilities['table']: multiplier *= .75
			digits = [cell['digit'] for cell in table.features[0] if 'digit' in cell]
			digits += [row[0]['digit'] for row in table.features if 'digit' in row[0]]
			multiplier *= sum(1 for d in digits if d == 0) / len(digits)
		data_area = [d for row in data_area for d in row]
		score = multiplier * sum(_compute_score_functions[d] for d in data_area) / len(data_area)
	table.score = max(0, min(1, score))

class Table:
	def __init__(self, url=None, element=None, xpath=None, materialize=False):
		self.url = url
		self.xpath = xpath
		self.element = element
		self.features = None
		self.texts = None
		self.contextual_info = None
		self.functions = None
		self.variabilities = {'row': None, 'col': None, 'table': None}
		self.kind = 'unknown'
		self.record = None
		self.score = None
		self.error = None

	def rows(self):
		return len(self.features)

	def cols(self):
		if self.rows():
			return len(self.features[0])
		else:
			return 0

	def json(self):
		res = [
			self.url,
			self.score,
			self.texts,
			self.features,
			self.variabilities,
			self.functions,
			self.kind,
			self.record,
			self.html(add_features=False)
		]
		return dumps(res, ensure_ascii=False, separators=(',', ':'))

	def html(self, add_features=True):
		res = f'<h2>{self.kind.capitalize()} <code>{self.url}${self.element["data-xpath"]}</code>'
		if self.error is None:
			res += '<samp>%05.2f%%</samp></h2><div class=\"table-info\"><table>' % (100 * self.score)
			for r, row in enumerate(self.features):
				res += '<tr>'
				for c, cell in enumerate(row):
					if add_features:
						raw_feats = list(sorted(k for k in cell if "variability" not in k))
						structured_feats = {f: [cell[f], cell["row-variability-" + f], cell["col-variability-" + f], cell["tab-variability-" + f]] for f in raw_feats}
						structured_feats = dumps(structured_feats, ensure_ascii=False).replace('"', "&quot;")
						structured_feats = f' data-features="{structured_feats}"'
					else:
						structured_feats = ''
					res += f'<td class="{FUNCTIONS[self.functions[r][c]]}"{structured_feats}>{self.texts[r][c]}</td>'
				res += '</tr>'
			res += '''</table><h3>Variabilities:</h3><ul>
			<li>Rows: <code>%.4f</code></li>
			<li>Columns: <code>%.4f</code></li>
			<li>Cells: <code>%.4f</code></li>
			</ul><h3>Interpretation</h3>
			<pre>%s</pre></div>''' % (
				self.variabilities['row'],
				self.variabilities['col'],
				self.variabilities['table'],
				dumps(self.record, ensure_ascii=False, indent="\t")
			)
		else:
			res += f'</h2><div class="table-info"><pre class="error">{self.error}</pre></div>'
		return res

	def metadata(self, min_majority=.8):
		''' Returns a datamart schema, assigning types to each variable, if at
		least min_majority of the values are of that type. '''
		lang = self.url.split('.', 1)[0].split('/')[-1]
		pg = Wikipedia(lang).page(self.url.rsplit('/', 1)[-1])
		kws = [kw.lower().split(':')[-1] for kw in pg.categories]
		kws = [kw for kw in kws if not any(c in kw for c in WIKIPEDIA_IGNORE_CATEGORIES)]
		kws = set(word for kw in kws for word in findall(r'\w+', kw) if not len(FIND_STOPWORDS(kw)))
		res = {
			"title": self.contextual_info[0] if len(self.contextual_info) else '',
			"description": pg.summary.split('\n', 1)[0],
			"url": self.url,
			"keywords": list(kws),
			"date_updated": pg.touched,
			"provenance": "wikipedia.org",
			"materialization": {
				"python_path": "wikitables_materializer",
				"arguments": {
					"url": self.url,
					"xpath": self.xpath,
					"materialize": True,
				}
			}
		}
		res['variables'] = []
		for name in self.record[0].keys():
			var = {'name': name, 'semantic_type': []}
			values = [r[name] for r in self.record]
			min_sample = min_majority * len(values)
			dates = [d for d in map(find_dates, values) if d != None]
			if len(dates) >= min_sample:
				var['semantic_type'].append('https://metadata.datadrivendiscovery.org/types/Time')
				var['temporal_coverage'] = {'start': min(dates), 'end': max(dates)}
			entities = {v: t for v in values for v, t in find_entities(v).items()}
			locations = [v for v, t in entities.items() if t == 'GPE']
			if len(locations) >= min_sample:
				var['semantic_type'].append('https://metadata.datadrivendiscovery.org/types/Location')
			people = [v for v, t in entities.items() if t == 'PERSON']
			if len(people):
				var['semantic_type'].append('https://schema.org/Person')
			if len(entities) >= min_sample:
				var['named_entity'] = list(entities.keys())
			numbers = [float(n) for n in values if n.strip().replace('.', '', 1).isdigit()]
			ranges = [n for n in values if BOOLEAN_SYNTAX_PROPERTIES['range'](n) is not None]
			if len(numbers) >= min_sample:
				var['semantic_type'].append('http://schema.org/Float')
			elif len(ranges) >= min_sample:
				var['semantic_type'].append('https://metadata.datadrivendiscovery.org/types/Interval')
			if not len(var['semantic_type']):
				if any(len(c) for c in values):
					var['semantic_type'] = 'http://schema.org/Text'
				else:
					var['semantic_type'] = 'https://metadata.datadrivendiscovery.org/types/MissingData'
			res['variables'].append(var)
		return res

	def dataframe(self):
		data = {}
		for col in self.record[0].keys():
			data[col] = [r[col] for r in self.record]
		return DataFrame(data=data)