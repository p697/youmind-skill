#!/usr/bin/env node
/**
 * md_to_base64.mjs
 *
 * Convert markdown text → Yjs binary base64 compatible with YouMind's editor.
 * Pipeline: Markdown → HTML (markdown-it) → Tiptap JSON → Yjs binary → base64
 *
 * Usage:
 *   echo "# Hello" | node scripts/md_to_base64.mjs
 *   node scripts/md_to_base64.mjs < input.md
 *
 * Output: a single base64 line
 */

import { createRequire } from 'module';
const require = createRequire(import.meta.url);

import { JSDOM } from 'jsdom';
import markdownit from 'markdown-it';
import { Doc, encodeStateAsUpdate } from 'yjs';
import { prosemirrorJSONToYXmlFragment } from 'y-prosemirror';
import { generateJSON } from '@tiptap/html';
import { getSchema } from '@tiptap/core';

// ESM-compatible imports for extensions that may be CJS
const { default: Document }        = await import('@tiptap/extension-document');
const { default: Paragraph }       = await import('@tiptap/extension-paragraph');
const { default: Text }            = await import('@tiptap/extension-text');
const { default: Heading }         = await import('@tiptap/extension-heading');
const { default: Bold }            = await import('@tiptap/extension-bold');
const { default: Italic }          = await import('@tiptap/extension-italic');
const { default: Strike }          = await import('@tiptap/extension-strike');
const { default: Code }            = await import('@tiptap/extension-code');
const { default: CodeBlock }       = await import('@tiptap/extension-code-block');
const { default: BulletList }      = await import('@tiptap/extension-bullet-list');
const { default: OrderedList }     = await import('@tiptap/extension-ordered-list');
const { default: ListItem }        = await import('@tiptap/extension-list-item');
const { default: Blockquote }      = await import('@tiptap/extension-blockquote');
const { default: HorizontalRule }  = await import('@tiptap/extension-horizontal-rule');
// Table extensions export named, not default
const { Table }       = await import('@tiptap/extension-table');
const { TableRow }    = await import('@tiptap/extension-table');
const { TableCell }   = await import('@tiptap/extension-table');
const { TableHeader } = await import('@tiptap/extension-table');

// YouMind's Yjs fragment key
const DOC_FRAGMENT = 'content';

const extensions = [
  Document,
  Paragraph,
  Text,
  Heading.configure({ levels: [1, 2, 3, 4, 5, 6] }),
  Bold,
  Italic,
  Strike,
  Code,
  CodeBlock,
  BulletList,
  OrderedList,
  ListItem,
  Blockquote,
  HorizontalRule,
  Table.configure({ resizable: false }),
  TableRow,
  TableCell,
  TableHeader,
];

const schema = getSchema(extensions);

// markdown-it
const md = markdownit({ html: false, linkify: true, breaks: false });

// Polyfill browser DOM for @tiptap/html in Node environment
const dom = new JSDOM('<!DOCTYPE html>');
global.window    = dom.window;
global.document  = dom.window.document;
global.DOMParser = dom.window.DOMParser;
global.HTMLElement = dom.window.HTMLElement;
global.Element   = dom.window.Element;
global.Node      = dom.window.Node;

function uint8ArrayToBase64(arr) {
  const CHUNK = 8192;
  let binary = '';
  for (let i = 0; i < arr.length; i += CHUNK) {
    binary += String.fromCharCode(...arr.subarray(i, i + CHUNK));
  }
  return Buffer.from(binary, 'binary').toString('base64');
}

function markdownToBase64(markdown) {
  const html  = md.render(markdown);
  const json  = generateJSON(html, extensions);
  const ydoc  = new Doc();
  const frag  = ydoc.getXmlFragment(DOC_FRAGMENT);
  prosemirrorJSONToYXmlFragment(schema, json, frag);
  return uint8ArrayToBase64(encodeStateAsUpdate(ydoc));
}

async function main() {
  let markdown = '';
  if (process.argv[2]) {
    markdown = process.argv[2].replace(/\\n/g, '\n');
  } else {
    process.stdin.setEncoding('utf8');
    for await (const chunk of process.stdin) markdown += chunk;
  }
  if (!markdown.trim()) {
    process.stderr.write('Error: no markdown input\n');
    process.exit(1);
  }
  try {
    process.stdout.write(markdownToBase64(markdown) + '\n');
  } catch (err) {
    process.stderr.write(`Error: ${err.message}\n${err.stack}\n`);
    process.exit(1);
  }
}

main();
