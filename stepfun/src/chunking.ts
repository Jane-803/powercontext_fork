export const MAX_CHARS = 900;
export const OVERLAP = 120;

export function splitText(text: string): string[] {
  const normalized = text.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  if (!normalized) return [];
  const paragraphs = normalized.split(/\n\s*\n/);
  const chunks: string[] = [];
  let current = "";
  for (const paragraph of paragraphs) {
    if ((current + "\n\n" + paragraph).length <= MAX_CHARS) {
      current = current ? `${current}\n\n${paragraph}` : paragraph;
      continue;
    }
    if (current) chunks.push(current);
    if (paragraph.length <= MAX_CHARS) {
      current = paragraph;
      continue;
    }
    for (let offset = 0; offset < paragraph.length; offset += MAX_CHARS - OVERLAP) {
      chunks.push(paragraph.slice(offset, offset + MAX_CHARS));
    }
    current = "";
  }
  if (current) chunks.push(current);
  return chunks;
}
