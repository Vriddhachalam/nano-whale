/// Remove ANSI escape sequences (colors, cursor) so TUI width and glyphs stay stable.
pub fn strip_ansi(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut it = s.chars().peekable();
    while let Some(c) = it.next() {
        if c == '\x1b' {
            if it.next_if(|&x| x == '[').is_some() {
                while let Some(&ch) = it.peek() {
                    it.next();
                    if ch == 'm' || ('@'..='~').contains(&ch) {
                        break;
                    }
                }
            }
            continue;
        }
        out.push(c);
    }
    out
}

/// One terminal row; never wider than `max_chars`.
pub fn clip_line(line: &str, max_chars: usize) -> String {
    if line.chars().count() <= max_chars {
        return line.to_string();
    }
    line.chars()
        .take(max_chars.saturating_sub(1))
        .chain(['…'])
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_color_codes() {
        let raw = "\x1b[32m[nodemon]\x1b[0m starting";
        assert_eq!(strip_ansi(raw), "[nodemon] starting");
    }
}
