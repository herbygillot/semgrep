from pathlib import Path
import traceback
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set

from semgrep.rule import Rule
from semgrep.rule_match import RuleMatch
from semgrep.util import print_error_exit
from semgrep.util import print_msg


def _generate_fix(rule: Rule, rule_match: RuleMatch) -> Optional[Any]:
    fix_str = rule.fix
    if fix_str is None:
        return None
    if "metavars" in rule_match.extra:
        for metavar, contents in rule_match.metavars.items():
            fix_str = fix_str.replace(metavar, contents["abstract_content"])
    return fix_str


def _modify_file(rule_match: RuleMatch, fix: str, use_git_conflict_markers: bool) -> None:
    p = Path(rule_match.path)
    SPLIT_CHAR = "\n"
    contents = p.read_text()
    lines = contents.split(SPLIT_CHAR)

    # get the start and end points
    start_obj = rule_match.start
    start_line = start_obj.get("line", 1) - 1  # start_line is 1 indexed
    start_col = start_obj.get("col", 1) - 1  # start_col is 1 indexed
    end_obj = rule_match.end
    end_line = end_obj.get("line", 1) - 1  # end_line is 1 indexed
    end_col = end_obj.get("col", 1) - 1  # end_line is 1 indexed

    # break into before, to modify, after
    before_lines = lines[:start_line]
    before_on_start_line = lines[start_line][:start_col]
    after_on_end_line = lines[end_line][end_col + 1 :]  # next char after end of match
    unmodified_lines = lines[start_line:end_line + 1] # TODO
    modified_lines = (before_on_start_line + fix + after_on_end_line).splitlines()
    after_lines = lines[end_line + 1 :]  # next line after end of match

    if use_git_conflict_markers:
        # desired output:
        # <<<<<<< HEAD
        # some_function('a') # original line
        # =======
        # some_other_function('b') # our autofix
        # >>>>>>> semgrep-patch-<ruleid>
        start_patch_mark = "<<<<<<< HEAD"
        middle_patch_mark = "======="
        end_patch_mark = f">>>>>>> semgrep-patch-{rule_match.id}"
        contents_after_fix = before_lines + [start_patch_mark] + unmodified_lines + [middle_patch_mark] + modified_lines + [end_patch_mark] + after_lines
    else:
        contents_after_fix = before_lines + modified_lines + after_lines

    contents_after_fix_str = SPLIT_CHAR.join(contents_after_fix)
    p.write_text(contents_after_fix_str)


def apply_fixes(rule_matches_by_rule: Dict[Rule, List[RuleMatch]]) -> None:
    """
        Modify files in place for all files with findings from rules with an
        autofix configuration
    """
    modified_files: Set[Path] = set()

    for rule, rule_matches in rule_matches_by_rule.items():
        for rule_match in rule_matches:
            fix = _generate_fix(rule, rule_match)
            if fix:
                filepath = rule_match.path
                try:
                    _modify_file(rule_match, fix, True) 
                    modified_files.add(filepath)
                except Exception as e:
                    print_error_exit(f"unable to modify file: {filepath}: {e} {traceback.format_exc()}")
    num_modified = len(modified_files)
    print_msg(
        f"Successfully modified {num_modified} file{'s' if num_modified > 1 else ''}."
    )
