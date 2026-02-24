#!/usr/bin/env python3
"""
Sport Program Parser
Parses sport program definition files and manages program state.
"""

import os
import re
from datetime import datetime, timedelta


class SportProgram:
    """Represents a sport program with segments"""

    def __init__(self, filename, name):
        self.filename = filename
        self.name = name
        self.segments = []  # List of (segment_number, level) tuples
        self.total_segments = 0
        self.duration_minutes = 0  # User specified duration
        self.segment_duration = 0  # Duration per segment (in seconds)
        self.start_time = None
        self.current_segment = 0
        self.completed = False

    def calculate_segment_duration(self):
        """Calculate duration per segment based on total duration"""
        if self.total_segments > 0:
            self.segment_duration = (
                self.duration_minutes * 60) / self.total_segments
        else:
            self.segment_duration = 0

    def get_current_level(self):
        """Get the current level based on elapsed time"""
        if not self.start_time or self.completed:
            return None

        elapsed = (datetime.now() - self.start_time).total_seconds()
        segment_num = int(elapsed / self.segment_duration) + 1

        if segment_num > self.total_segments:
            self.completed = True
            segment_num = self.total_segments

        # Find the level for this segment
        current_level = None
        for seg_num, level in self.segments:
            if segment_num >= seg_num:
                current_level = level
            else:
                break

        self.current_segment = segment_num
        return current_level

    def get_progress(self):
        """Get progress as percentage and remaining time"""
        if not self.start_time or self.segment_duration == 0:
            return 0.0, 0.0, 0

        elapsed = (datetime.now() - self.start_time).total_seconds()
        total_duration = self.duration_minutes * 60

        if elapsed >= total_duration:
            return 100.0, 0.0, self.current_segment

        progress = (elapsed / total_duration) * 100
        remaining = total_duration - elapsed

        return progress, remaining, self.current_segment

    def get_current_segment_info(self):
        """Get info about current segment"""
        if not self.start_time or self.current_segment == 0:
            return None, 0, 0

        # Find level for current segment
        current_level = None
        next_level = None
        for seg_num, level in self.segments:
            if self.current_segment >= seg_num:
                current_level = level
            else:
                next_level = level
                break

        # Calculate time remaining in current segment
        elapsed = (datetime.now() - self.start_time).total_seconds()
        elapsed_in_segment = elapsed - \
            ((self.current_segment - 1) * self.segment_duration)
        remaining_in_segment = max(
            0, self.segment_duration - elapsed_in_segment)

        return current_level, remaining_in_segment, self.current_segment

    def start(self):
        """Start the program"""
        self.start_time = datetime.now()
        self.completed = False
        self.current_segment = 0


class SportProgramParser:
    """Parser for sport program definition files"""

    def __init__(self, programs_dir="sport_programs"):
        self.programs_dir = programs_dir
        self.programs = {}

    def load_programs(self):
        """Load all programs from the programs directory"""
        self.programs = {}

        if not os.path.exists(self.programs_dir):
            print(f"Programs directory '{self.programs_dir}' not found")
            return self.programs

        for filename in os.listdir(self.programs_dir):
            if filename.endswith('.txt'):
                filepath = os.path.join(self.programs_dir, filename)
                program = self.parse_file(filepath)
                if program:
                    self.programs[filename] = program

        return self.programs

    def parse_file(self, filepath):
        """Parse a single program file"""
        try:
            with open(filepath, 'r') as f:
                content = f.read()

            # Extract name from filename (remove .txt)
            name = os.path.basename(filepath).replace(
                '.txt', '').replace('_', ' ').title()

            program = SportProgram(filepath, name)

            # Parse SEGMENTS line
            segments_match = re.search(r'SEGMENTS:(\d+)', content)
            if segments_match:
                program.total_segments = int(segments_match.group(1))

            # Parse SEG lines - format: SEG:segment_number:level
            seg_matches = re.findall(r'SEG:(\d+):(\d+)', content)
            for seg_num, level in seg_matches:
                program.segments.append((int(seg_num), int(level)))

            # Sort segments by segment number
            program.segments.sort(key=lambda x: x[0])

            return program

        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None

    def get_program(self, filename):
        """Get a specific program by filename"""
        return self.programs.get(filename)

    def list_programs(self):
        """List all available programs"""
        return list(self.programs.values())
