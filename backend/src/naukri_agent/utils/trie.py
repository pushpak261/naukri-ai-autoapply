"""
Aho-Corasick Multi-Pattern Search Automaton and Trie implementation.
"""

from __future__ import annotations

from collections import deque


class TrieNode:
    """A node in the Trie structure for the Aho-Corasick automaton."""

    def __init__(self, char: str = "") -> None:
        self.char = char
        self.children: dict[str, TrieNode] = {}
        self.fail: TrieNode | None = None
        self.output: list[str] = []


class AhoCorasick:
    """
    Aho-Corasick Automaton for fast multi-keyword matching in text.
    Time Complexity:
        - Construction: O(Sum of keyword lengths)
        - Search: O(N + K) where N is text length and K is match count
    """

    def __init__(self, keywords: list[str]) -> None:
        self.root = TrieNode()
        self._build_trie(keywords)
        self._build_automaton()

    def _build_trie(self, keywords: list[str]) -> None:
        """Insert keywords into the trie."""
        for kw in keywords:
            clean_kw = kw.strip().lower()
            if not clean_kw:
                continue
            curr = self.root
            for char in clean_kw:
                if char not in curr.children:
                    curr.children[char] = TrieNode(char)
                curr = curr.children[char]
            # Store the original pattern to preserve casing/metadata in matches
            curr.output.append(kw)

    def _build_automaton(self) -> None:
        """Establish suffix (failure) and dictionary/output links using BFS."""
        queue: deque[TrieNode] = deque()

        # Step 1: Set failure links for depth 1 nodes to the root
        for child in self.root.children.values():
            child.fail = self.root
            queue.append(child)

        # Step 2: Establish links for depth > 1 using BFS
        while queue:
            curr = queue.popleft()

            for char, child in curr.children.items():
                fail_node = curr.fail
                while fail_node is not None and char not in fail_node.children:
                    fail_node = fail_node.fail

                child.fail = fail_node.children[char] if fail_node else self.root

                # Merge output pattern matches of failure state (dictionary links)
                if child.fail:
                    child.output.extend(child.fail.output)

                queue.append(child)

    def search(self, text: str) -> dict[str, list[int]]:
        """
        Search the input text for any occurrences of the configured keywords.

        Args:
            text: The text string to search within.

        Returns:
            A dictionary mapping matched keywords to a list of their start indices in the text.
        """
        results: dict[str, list[int]] = {}
        if not text:
            return results

        curr = self.root
        text_lower = text.lower()

        for idx, char in enumerate(text_lower):
            while curr is not None and char not in curr.children:
                curr = curr.fail

            if curr is None:
                curr = self.root
                continue

            curr = curr.children[char]
            for pattern in curr.output:
                if pattern not in results:
                    results[pattern] = []
                start_idx = idx - len(pattern) + 1
                results[pattern].append(start_idx)

        return results
