export function advance(index, length) {
  return Math.min(index + 1, length - 1);
}
export function writeWord(values, cells, index, text) {
  let last = index;
  for (const char of text.slice(0, cells.length - index)) {
    values[cells[last].join(",")] = char;
    last++;
  }
  return Math.min(last, cells.length - 1);
}
export function erase(values, cells, index) {
  if (!values[cells[index].join(",")] && index > 0) index--;
  delete values[cells[index].join(",")];
  return index;
}
