from __future__ import print_function

import logging
import glob
import sys

from config import *

def read_filenames(arg, config):
    # File containing lines of the form:
    #  raw_filename [output_filename [cur_line cur_token [other_annotations]]]
    #
    if len(glob.glob(arg)) == 0:
        raise Exception("Cannot open / find '{}'".format(arg))
    file_info = [line.strip() for line in open(arg).readlines()]
    filenames = []
    for line in file_info:
        parts = line.split()
        raw_file = parts[0]
        position = [0, 0]
        output_file = raw_file + ".annotations"
        annotations = []
        if len(parts) > 1:
            output_file = parts[1]
        if len(parts) > 3:
            position = [int(parts[2]), int(parts[3])]
        if len(parts) > 4:
            # Additional annotations (used when comparing annotations)
            annotations = parts[4:]
        filenames.append((raw_file, position, output_file, annotations))

    # Check files exist (or do not exist if being created)
    missing = []
    extra = []
    for raw_file, _, output_file, annotations in filenames:
        if len(glob.glob(raw_file)) == 0:
            missing.append(raw_file)
        if not config.args.overwrite:
            if len(glob.glob(output_file)) != 0:
                extra.append(output_file)
        for annotation in annotations:
            if len(glob.glob(annotation)) == 0:
                missing.append(annotation)
    if len(missing) > 0 or len(extra) > 0:
        error = "Input Filename List Has Errors"
        if len(missing) > 0:
            error += "\n\nUnable to open:\n" + '\n'.join(missing)
        if len(extra) > 0:
            error += "\n\nOutput file already exists:\n" + '\n'.join(extra)
        raise Exception(error)
    return filenames

def get_num(text):
    # TODO: Switch to simple regex
    mod_text = []
    for char in text:
        if char not in '(),':
            mod_text.append(char)
    return int(''.join(mod_text))

def read_annotation_file(config, filename):
    marked = {}

    # Read standoff annotations if they exist. Note:
    #  - Whitespace variations are ignored.
    #  - Repeated labels / links are ignored.
    if len(glob.glob(filename)) != 0:
        for line in open(filename):
            fields = line.strip().split()
            if config.annotation == AnnScope.token:
                # All examples refer to word 2 on line 4
                source = (get_num(fields[0]), get_num(fields[1]))
                if config.annotation_type == AnnType.categorical:
                    # Format example:
                    # (4, 2) - buy sell
                    # means (4, 2) is labeled 'buy' and 'sell'
                    labels = set(fields[3:])
                    marked[source] = labels
                elif config.annotation_type == AnnType.link:
                    # Format example:
                    # (4, 2) - (4, 1) (4, 0)
                    # means (4, 2) is linked to the two words before it
                    targets = set()
                    for i in range(3, len(fields), 2):
                        line = get_num(fields[i])
                        token = get_num(fields[i + 1])
                        targets.add((line, token))
                    marked[source] = targets
                elif config.annotation_type == AnnType.text:
                    # Format example:
                    # (4, 2) - blah blah blah
                    # means (4, 2) is labeled "blah blah blah"
                    marked[source] = ' '.join(fields[3:])
###            elif config.annotation == AnnScope.span:
###                # All examples refer to a span from word 2 on line 4 to word 1 on line 6
###                source_start = (get_num(fields[0]), get_num(fields[1]))
###                source_end = (get_num(fields[2]), get_num(fields[3]))
###                source = (source_start, source_end)
###                if config.annotation_type == AnnType.categorical:
###                    # Format example:
###                    # ((4, 2), (6, 1) - buy sell
###                    labels = set(fields[5:])
###                    marked[source] = labels
###                elif config.annotation_type == AnnType.link:
###                    # Format example:
###                    # ((4, 2), (6, 1) - ((0, 0), (0, 4)), ((1,0), (1,2))
###                    targets = set()
###                    for i in range(5, len(fields), 4):
###                        start = (get_num(fields[i]), get_num(fields[i + 1]))
###                        end = (get_num(fields[i + 2]), get_num(fields[i + 3]))
###                        targets.add((start, end))
###                    marked[source] = targets
###                elif config.annotation_type == AnnType.text:
###                    # Format example:
###                    # ((4, 2), (6, 1)) - blah blah blah
###                    # means (4, 2) is labeled "blah blah blah"
###                    marked[source] = ' '.join(fields[3:])
            elif config.annotation == AnnScope.line:
                source = int(fields[0])
                if config.annotation_type == AnnType.categorical:
                    # Format example:
                    # 3 - buy sell
                    # means line 3 is labeled 'buy' and 'sell'
                    marked[source] = set(fields[2:])
                elif config.annotation_type == AnnType.link:
                    # Format example:
                    # 3 - 4 1
                    # means line 3 is linked to lines 1 and 4
                    targets = {int(v) for v in fields[2:]}
                    marked[source] = targets
                elif config.annotation_type == AnnType.text:
                    # Format example:
                    # 3 - blah blah
                    # means line 3 is labeled "blah blah"
                    marked[source] = ' '.join(fields[2:])
    return marked

def compare_nums(num0, num1):
    if num0 < num1:
        return -1
    elif num0 == num1:
        return 0
    else:
        return 1

def compare_pos(config, pos0, pos1):
    if config.annotation == AnnScope.line:
        return compare_nums(pos0, pos1)
    else:
        comparison = compare_nums(pos0[0], pos1[0])
        if comparison == 0:
            return compare_nums(pos0[1], pos1[1])
        else:
            return comparison

def prepare_for_return(config, pos):
    if config.annotation != AnnScope.line:
        return pos
    elif pos == -1:
        return [-1, -1]
    else:
        return [pos, 0]

class Document(object):
    """Storage for the raw text data."""
    # TODO: Think about maintaining whitespace variations

    def __init__(self, filename):
        self.tokens = []
        self.first_char = None
        self.last_char = None
        for line in open(filename):
            cur = []
            self.tokens.append(cur)
            for token in line.strip().split():
                if self.first_char is None:
                    self.first_char = (len(self.tokens) - 1, 0, 0)
                self.last_char = (len(self.tokens) - 1, len(cur), len(token) - 1)
                cur.append(token)
        assert self.first_char is not None, "Empty document"

    def get_moved_pos(self, pos, right=0, down=0, jump=False):
        # TODO: long-jump as well as jump, have jump do a smaller scale
        if len(pos) == 0:
            # This is the whole document, can't move
            return pos
        elif len(pos) == 1:
            # This is a line, ignore right
            # Note, an empty line can be selected
            npos = min(len(self.tokens) - 1, max(0, pos[0] + down))
            if jump and down < 0: npos = 0
            if jump and down > 0: npos = len(self.tokens) - 1
            return (npos)
        elif len(pos) == 2:
            # Moving a token
            # Vertical movement
            nline = pos[0]
            if jump:
                # We always want to be on a token, so go to the first or last
                # line with one.
                if down < 0: nline = self.first_char(0)
                elif down > 0: nline = self.last_char(0)
            else:
                # Shift incrementally because we only want to count lines that
                # have tokens.
                shift = down
                delta = 1 if shift > 0 else -1
                while shift != 0 and self.first_char(0) < nline < self.last_char(0):
                    nline += delta
                    if len(self.tokens[nline]) > 0:
                        shift -= delta

            # Horizontal movement
            ntok = pos[1]
            if jump:
                if right < 0: ntok = 0
                elif right > 0: ntok = len(self.tokens[nline]) - 1
            else:
                shift = right
                delta = 1 if shift > 0 else -1
                while shift != 0:
                    if delta == -1 and nline == self.first_char(0) and ntok == self.first_char(1):
                        break
                    if delta == 1 and nline == self.last_char(0) and ntok == self.last_char(1):
                        break
                    if 0 <= ntok + delta < len(self.tokens[nline]):
                        ntok += delta
                    else:
                        # Go forward/back to a line with tokens. Note, we know
                        # there are later/earlier lines, since otherwise we would
                        # have been at the last_char/first_char position.
                        nline += delta
                        while len(self.tokens[nline]) == 0:
                            nline += delta
                        ntok = 0 if delta > 0 else len(self.tokens[nline]) - 1
                    shift -= delta
            return (nline, ntok)
        else:
            # Moving a character
            # Vertical movement
            nline = pos[0]
            if jump:
                # We always want to be on a character, so go to the first or last
                # line with one.
                if down < 0: nline = self.first_char(0)
                elif down > 0: nline = self.last_char(0)
            else:
                # Shift incrementally because we only want to count lines that
                # have characters.
                shift = down
                delta = 1 if shift > 0 else -1
                while shift != 0 and self.first_char(0) < nline < self.last_char(0):
                    nline += delta
                    if len(self.tokens[nline]) > 0:
                        shift -= delta

            # Horizontal movement
            ntok = pos[1]
            nchar = pos[2]
            if jump:
                if right < 0:
                    ntok = 0
                    nchar = 0
                elif right > 0:
                    ntok = len(self.tokens[nline]) - 1
                    nchar = len(self.tokens[nline][ntok]) - 1
            else:
                shift = right
                delta = 1 if shift > 0 else -1
                while shift != 0:
                    if delta == -1 and \
                            nline == self.first_char(0) and \
                            ntok == self.first_char(1) and \
                            nchar == self.first_char(1):
                        break
                    if delta == 1 and \
                            nline == self.last_char(0) and \
                            ntok == self.last_char(1) and \
                            nchar == self.last_char(1):
                        break
                    if 0 < nchar + delta < len(self.tokens[nline][ntok]) - 1:
                        nchar += delta
                    elif delta < 0 and ntok > 0:
                        ntok -= 1
                        nchar = len(self.tokens[nline][ntok]) - 1
                    elif delta > 0 and ntok < len(self.tokens[nline]) - 1:
                        ntok += 1
                        nchar = 0
                    else:
                        # Go forward/back to a line with tokens. Note, we know
                        # there are later/earlier lines, since otherwise we would
                        # have been at the last_char/first_char position.
                        nline += delta
                        while len(self.tokens[nline]) == 0:
                            nline += delta
                        ntok = 0 if delta > 0 else len(self.tokens[nline]) - 1
                        nchar = 0 if delta > 0 else len(self.tokens[nline][ntok]) - 1
                    shift -= delta
            return (nline, ntok, nchar)

class Span(object):
    """A continuous span of text.
    
    All annotations are on spans, some of which just happen to have a single element."""

    def __init__(self, scope, doc, span=None):
        self.doc = doc
        self.start = None
        self.end = None
        if scope == AnnScope.character:
            self.start, self.end = (0, 0, 0), (0, 0, 1)
        elif scope == AnnScope.token:
            self.start, self.end = (0, 0), (0, 1)
        elif scope == AnnScope.line:
            self.start, self.end = (0), (1)
        elif scope == AnnScope.document:
            self.start, self.end = (), ()
        else:
            raise Exception("Invalid scope")
        if span is not None:
            # Most of the time a span will be provided to start from.
            self.end = span.end
            self.start = span.start

    def __hash__(self):
        return hash((self.start, self.end))

    # Modification functions, each returns the position that was modified
    def edit_left(self, moving=True, shift=False):
        if len(self.start) == 0:
            pass # Do nothing for full document cases
        elif moving:
            if shift:
                pass # Jump to start of [doc, line, token]
            else:
                pass # Move to previous [line, token, character]
        else:
            if shift:
                pass # Move start of the span
            else:
                pass # Move end of the span
    def edit_right(self, shift=False):
        if len(self.start) == 0: return
        pass
    def edit_up(self, shift=False):
        if len(self.start) == 0: return
        pass
    def edit_down(self, shift=False):
        if len(self.start) == 0: return
        pass

    def change_ann_type(self):
        pass

    # How to do coreference resolution annotation:
    # Normally, have a single position, left =, right, etc move it.
    # Pressing 'a' makes it a mention and switches into linking mode.
    # Pressing 'A' switches into a span specification mode, where movement
    # edits the extent of the span, and pressing 'a' completes it and switches
    # into linking mode.
    # In linking mode, movement allows choosing between previous clusters
    # (starting with 'no cluster').
    # Pressing 'c' creates the link and switches back to regular mode.
    # Note, in the initial mode, if a span is highlighted, 's' will select it,
    # and 'S' will select it and go into span editing mode.
    #
    # This allows for construction of items, editing, multi-token spans,
    # linking, nesting.

class Item(object):
    """One or more spans and a set of labels.

    This is used in Datum to keep track of annotations, and used in View to determine the current appearance."""
    def __init__(self):
        self.spans = []
        self.labels = set()

class Datum(object):
    """Storage for a single file's data and annotations.

    Note, the structure of storage depends on the annotation type."""

    def __init__(self, filename, config, output_file, annotation_files):
        self.filename = filename
        self.annotation_files = annotation_files
        self.config = config
        self.output_file = output_file

        self.marked = read_annotation_file(config, self.output_file)
        self.in_link = {}
        if self.config.annotation_type == AnnType.link:
            for pos in self.marked:
                for opos in self.marked[pos]:
                    if opos not in self.in_link:
                        self.in_link[opos] = 0
                    self.in_link[opos] += 1

        self.tokens = []
        self.lines = []
        for line in open(filename):
            self.tokens.append([])
            self.lines.append(line.strip())
            for token in line.split():
                self.tokens[-1].append(token)

        # TODO: Work out how to handle the AnnType.text case
        self.marked_compare = {}
        self.markings = []
        for filename in self.annotation_files:
            other_marked = read_annotation_file(config, filename)
            self.markings.append(other_marked)
            for key in other_marked:
                for label in other_marked[key]:
                    current = self.marked_compare.setdefault(key, {})
                    current[label] = current.get(label, 0) + 1

        self.disagree = set()
        if len(self.annotation_files) > 1:
            for key in self.marked:
                for label in self.marked[key]:
                    if key not in self.marked_compare:
                        self.disagree.add(key)
                    elif label not in self.marked_compare[key]:
                        self.disagree.add(key)
            for key in self.marked_compare:
                for label in self.marked_compare[key]:
                    if key not in self.marked or label not in self.marked[key]:
                        self.disagree.add(key)
                    if self.marked_compare[key][label] != len(self.annotation_files):
                        self.disagree.add(key)

    def get_marked_token(self, pos, cursor, linking_pos):
        pos = tuple(pos)
        linking_pos = tuple(linking_pos)

        token = self.tokens[pos[0]][pos[1]]
        color = DEFAULT_COLOR
        text = None

        if self.config.annotation == AnnScope.line:
            pos = pos[0]
            linking_pos = linking_pos[0]
            cursor = cursor[0]
            # For categorical data, set the text
            if self.config.annotation_type == AnnType.categorical:
                text = ' '.join(self.marked.get(cursor, []))

        # If showing linked, set the default colour
        if self.config.args.show_linked:
            if pos in self.marked:
                if len(self.marked[pos]) > 0:
                    color = YELLOW_COLOR
            elif self.in_link.get(pos, 0) > 0:
                color = YELLOW_COLOR

        if pos == cursor:
            color = CURSOR_COLOR
            if pos == linking_pos:
                color = LINK_CURSOR_COLOR
            elif pos in self.marked.get(linking_pos, []):
                color = REF_CURSOR_COLOR
            else:
                count = self.marked_compare.get(linking_pos, {}).get(pos, -1)
                if count == len(self.annotation_files):
                    color = REF_CURSOR_COLOR
                elif count > 0:
                    color = COMPARE_REF_CURSOR_COLORS[min(count, 2) - 1]

            if self.config.annotation_type == AnnType.text:
                text = self.marked.get(pos)
        elif pos == linking_pos:
            color = LINK_COLOR
        else:
            if pos in self.disagree:
                if compare_pos(self.config, pos, cursor) > 0:
                    if compare_pos(self.config, pos, linking_pos) > 0:
                        color = COMPARE_DISAGREE_COLOR

            # Changed to give different colours, rather than count
            count = self.marked_compare.get(linking_pos, {}).get(pos, -1)
            if 0 < count < len(self.annotation_files):
                color = COMPARE_REF_COLORS[count - 1]
###            if 0 < count < 1+len(self.annotation_files):
###                if pos in self.marked.get(linking_pos, []):
###                    color = COMPARE_REF_COLORS[1]
###                else:
###                    color = COMPARE_REF_COLORS[0]

            if pos in self.marked or linking_pos in self.marked:
                if self.config.annotation_type == AnnType.categorical:
                   for key in self.marked.get(pos, []):
                        modifier = self.config.keys[key]
                        if color != DEFAULT_COLOR:
                            color = OVERLAP_COLOR
                        else:
                            color = modifier.color
                elif self.config.annotation_type == AnnType.link:
                    if pos in self.marked.get(linking_pos, []):
                        color = REF_COLOR

        return (token, color, text)

    def convert_to_key(self, pos):
        if self.config.annotation == AnnScope.line:
            return pos[0]
        else:
            return (pos[0], pos[1])

    def get_closest_disagreement(self, pos, options, before, check_disagree):
        closest = None
        for option in options:
            # Only consider cases where there was a disagreement
            if check_disagree:
                if option not in self.disagree:
                    continue
            elif options[option] == 1 + len(self.annotation_files):
                continue

            comparison = compare_pos(self.config, pos, option)
            if before and comparison <= 0:
                continue
            elif (not before) and comparison >= 0:
                continue

            if closest is None:
                closest = option
            else:
                comparison = compare_pos(self.config, closest, option)
                if before and comparison <= 0:
                    closest = option
                elif (not before) and comparison >= 0:
                    closest = option
        return closest

    def next_match(self, pos, limit, text, reverse):
        # TODO: Only implemented correctly for the line matching case at the
        # moment!
        npos = pos[:]
        delta = -1 if reverse else 1
        found = False
        npos[0] += delta
        while 0 <= npos[0] <= limit[0]:
            if text in self.lines[npos[0]]:
                found = True
                break
            npos[0] += delta

        if found:
            return npos
        else:
            return pos

    def next_disagreement(self, pos, linking_pos, reverse):
        if self.config.annotation == AnnScope.line:
            pos = pos[0]
            linking_pos = linking_pos[0]

        # First, move the pos
        marked = self.marked_compare
        if self.config.annotation_type == AnnType.link:
            marked = marked.get(linking_pos, {})
        closest = self.get_closest_disagreement(pos, marked, reverse, False)
        if closest is not None:
            return (prepare_for_return(self.config, closest),
                    prepare_for_return(self.config, linking_pos))

        # If that fails, and we are linking, move the linking_pos, then the pos
        if self.config.annotation_type == AnnType.link:
            marked = self.marked_compare
            closest_link = self.get_closest_disagreement(linking_pos, marked,
                    reverse, True)
            if closest_link is not None:
                comparison = (-1, -1)
                if reverse:
                    comparison = (sys.maxsize, sys.maxsize)
                if self.config.annotation == AnnScope.line:
                    comparison = comparison[0]

                marked = marked[closest_link]
                closest_pos = self.get_closest_disagreement(comparison,
                        marked, reverse, False)
                return (prepare_for_return(self.config, closest_pos),
                        prepare_for_return(self.config, closest_link))

        # If there are no disagreements, don't move at all
        return (prepare_for_return(self.config, pos),
                prepare_for_return(self.config, linking_pos))

    def add_to_in_link(self, pos):
        if self.config.annotation_type == AnnType.link:
            if pos not in self.in_link:
                self.in_link[pos] = 0
            self.in_link[pos] += 1

    def remove_from_in_link(self, pos):
        if self.config.annotation_type == AnnType.link:
            self.in_link[pos] -= 1

    def modify_annotation(self, pos, linking_pos, symbol=None):
        # Do not allow links from an item to itself
        if pos == linking_pos:
            return

        pos_key = self.convert_to_key(pos)
        item = symbol
        if self.config.annotation_type == AnnType.link:
            item = pos_key
            pos_key = self.convert_to_key(linking_pos)

        if pos_key not in self.marked:
            self.marked[pos_key] = {item}
            self.add_to_in_link(item)
        elif item not in self.marked[pos_key]:
            self.marked[pos_key].add(item)
            self.add_to_in_link(item)
        elif len(self.marked[pos_key]) == 1:
            # Given the first two conditions, we know there is a single
            # mark and it is this symbol.
            self.marked.pop(pos_key)
            self.remove_from_in_link(item)
        else:
            self.marked[pos_key].remove(item)
            self.remove_from_in_link(item)

    def remove_annotation(self, pos, ref):
        pos_key = self.convert_to_key(pos)
        if self.config.annotation_type == AnnType.link:
            pos_key = self.convert_to_key(ref)
        if pos_key in self.marked:
            for item in self.marked[pos_key]:
                self.remove_from_in_link(item)
            self.marked.pop(pos_key)

    def check_equal(self, pos0, pos1):
        if self.config.annotation == AnnScope.line:
            return pos0[0] == pos1[0]
        else:
            return pos0 == pos1

    def write_out(self, filename=None):
        out_filename = self.output_file
        if filename is not None:
            out_filename = filename
        out = open(out_filename, 'w')

        for key in self.marked:
            source = str(key)
            info = self.marked[key]
            if self.config.annotation_type == AnnType.categorical:
                info = " ".join([str(v) for v in info])
            elif self.config.annotation_type == AnnType.link:
                info = " ".join([str(v) for v in info])
            elif self.config.annotation_type == AnnType.text:
                pass
            print("{} - {}".format(source, info), file=out)
        out.close()

