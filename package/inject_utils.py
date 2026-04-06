"""Utility module to inject strings into code and data files."""
from pathlib import Path
import sys
import shutil

def print_msg(msg):
    """Prints a message to the console."""
    sys.stdout.write(f"{msg}\n")


class Injector:
    """Inject contents to ASCII files."""

    def __init__(self, file_path):
        self.file_path = None
        self.content = None
        self.search_list = None  # search content may be reversed or not

        self._search_direction = "forward"
        self._match_mode = "equal"
        self.force = True
        self.set_file_path(file_path)

    @property
    def search_direction(self):
        """Return defined search direction."""
        return self._search_direction

    @search_direction.setter
    def search_direction(self, value):
        """Set the search direction."""
        if value not in ["forward", "backward"]:
            raise ValueError("Invalid value")
        self._search_direction = value
        self.search_list = self.__get_search_list()

    @property
    def match_mode(self):
        """Return defined match mode."""
        return self._match_mode

    @match_mode.setter
    def match_mode(self, value):
        if value not in ["equal", "contains"]:
            raise ValueError("Invalid value")
        self._match_mode = value

    def set_file_path(self, value):
        """Sets the file path."""
        if isinstance(value, str):
            self.file_path = Path(value)
        elif isinstance(value, Path):
            self.file_path = value
        else:
            raise ValueError("Invalid value")
        self.content = self.read()
        self.search_list = self.__get_search_list()

    def __get_search_list(self):
        if self.search_direction == "forward":
            return self.content
        return self.content[::-1]

    def __add_content(self, new_content, head_end, tail_start):
        """Adds the new content to the content list.

        * `head_end` is the exclusive end index for the head slice (i.e. content[:head_end]).
        * `tail_start` is the start index for the tail slice (i.e. content[tail_start:]).
        """
        if isinstance(new_content, str):
            new_content = [new_content]

        if self.search_direction == "forward":
            added_content = self.content[
                                :head_end] + new_content + self.content[
                                tail_start:]
        else:
            length = len(self.content)
            original_head_end = length - head_end
            original_tail_start = length - 1 - tail_start
            added_content = (
                    self.content[
                        :original_head_end] + new_content + self.content[
                        original_tail_start:]
            )
        return added_content

    def inject_between(self, new_content, start_line, end_line,
                       suppress_warnings=False):
        """Inject `new_content` between the lines matching `start_line` and `end_line`."""
        if not self.file_path.is_file():
            if self.force:
                self._dump_content(self.content)
                print_msg(f"File {self.file_path} created with new content.")
                return True
            if not suppress_warnings:
                print_msg(f"File {self.file_path} not found. Aborting.")
            return False

        start_idx = self._find_index(self.search_list, start_line)
        if start_idx is None:
            if self.force:
                if not suppress_warnings:
                    print_msg(
                        "Start line not found. Injecting at the end of the file.")
                self._dump_content(self.content + new_content)
                return True
            if not suppress_warnings:
                print_msg("Start line not found. Aborting.")
            return False

        end_idx = self._find_index(self.search_list, end_line, begin_from=start_idx)
        if end_idx is None:
            if self.force:
                if not suppress_warnings:
                    print_msg(
                        "End line not found. Injecting at the end of the file.")
                self._dump_content(self.content + new_content)
                return True
            if not suppress_warnings:
                print_msg("End line not found. Aborting.")
            return False

        if end_idx <= start_idx:
            if not suppress_warnings:
                print_msg("End line occurs before start line. Aborting.")
            return False

        injected_content = self.__add_content(new_content, start_idx + 1,
                                              end_idx)
        self._dump_content(injected_content)
        return True

    def inject_after(self, new_content, line, suppress_warnings=False):
        """Injects the new content after the line."""
        if not self.file_path.is_file():
            if self.force:
                self._dump_content(self.content)
                print_msg(f"File {self.file_path} created with new content.")
                return True
            if not suppress_warnings:
                print_msg(f"File {self.file_path} not found. Aborting.")
            return False

        start_idx = self._find_index(self.search_list, line)
        if start_idx is None:
            if self.force:
                if not suppress_warnings:
                    print_msg(
                        "Line not found. Injecting at the end of the file.")
                self._dump_content(self.content + new_content)
                return True
            if not suppress_warnings:
                print_msg("Line not found. Aborting.")
            return False

        injected_content = self.__add_content(new_content, start_idx + 1,
                                              start_idx + 1)
        self._dump_content(injected_content)
        return True

    def inject_before(self, new_content, line, suppress_warnings=False):
        """Injects the new content before the line."""
        if not self.file_path.is_file():
            if self.force:
                self._dump_content(self.content)
                print_msg(f"File {self.file_path} created with new content.")
                return True
            if not suppress_warnings:
                print_msg(f"File {self.file_path} not found. Aborting.")
            return False
        start_idx = self._find_index(self.search_list, line)
        if not start_idx:
            if self.force:
                if not suppress_warnings:
                    print_msg("Line not found. Injecting at the end of the file.")
                self._dump_content(self.content + new_content)
                return True
            if not suppress_warnings:
                print_msg("Line not found. Aborting.")
            return False
        injected_content = self.__add_content(new_content, start_idx, start_idx)
        self._dump_content(injected_content)
        return True

    def replace_all(self, new_content):
        """Replace the whole file with the new content."""
        self._dump_content(new_content)
        return True

    def replace_single_line(self, new_content, line, suppress_warnings=False):
        """Replace the given line with the new content."""
        if isinstance(new_content, str):
            if not new_content.endswith("\n"):
                new_content = f"{new_content}\n"
            new_content = [new_content]

        if not self.file_path.is_file():
            if self.force:
                self._dump_content(self.content)
                print_msg(f"File {self.file_path} created with new content.")
                return True
            if not suppress_warnings:
                print_msg(f"File {self.file_path} not found. Aborting.")
            return False
        start_idx = self._find_index(self.search_list, line)
        if not start_idx:
            if self.force:
                if not suppress_warnings:
                    print_msg("Line not found. Injecting at the end of the file.")
                self._dump_content(self.content + new_content)
                return True
            if not suppress_warnings:
                print_msg("Line not found. Aborting.")
            return False
        injected_content = self.__add_content(new_content, start_idx, start_idx + 1)
        self._dump_content(injected_content)
        return True

    def replace_string(self, new_string, old_string, suppress_warnings=False):
        """Replace the old string with the new string. If the old string
        is not found, do nothing and return with a warning."""
        if not self.file_path.is_file():
            if self.force:
                self._dump_content(self.content)
                print_msg(f"File {self.file_path} created with new content.")
                return True
            if not suppress_warnings:
                print_msg(f"File {self.file_path} not found. Aborting.")
            return False
        new_content = []
        for line in self.content:
            if old_string in line:
                new_content.append(line.replace(old_string, new_string))
            else:
                new_content.append(line)
        if new_content == self.content:
            if not suppress_warnings:
                print_msg("String not found. Aborting.")
            return False
        self._dump_content(new_content)
        return True

    def read(self):
        """Reads the file."""
        if not self.file_path.is_file():
            self._dump_content([])
            return []
        with open(self.file_path, "r", encoding="utf-8") as file_data:
            if file_data.mode != "r":
                return None
            content_list = file_data.readlines()
        return content_list

    def _dump_content(self, list_of_lines):
        """Write the content to the file."""
        temp_file_path = (
            self.file_path.parent / f"{self.file_path.stem}_TMP{self.file_path.suffix}"
        )
        with open(temp_file_path, "w+", encoding="utf-8") as temp_file:
            temp_file.writelines(list_of_lines)
        shutil.move(temp_file_path, self.file_path)

    def _find_index(self, search_list, line, begin_from=0):
        """Get the index of a line in a list of lines."""
        if self.match_mode == "equal" and line in search_list:
            return search_list.index(line)

        if self.match_mode == "contains":
            for idx in range(begin_from, len(search_list)):
                if line in search_list[idx]:
                    return idx
        return None
