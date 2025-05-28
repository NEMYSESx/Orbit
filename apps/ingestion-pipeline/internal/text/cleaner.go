// internal/text/cleaner.go
package text

import (
	"regexp"
	"strings"
	"unicode"
)

type Cleaner struct {
	enabled bool
	
	multipleSpacesRegex   *regexp.Regexp
	multipleNewlinesRegex *regexp.Regexp
	controlCharsRegex     *regexp.Regexp
	htmlTagsRegex         *regexp.Regexp
}

func NewCleaner(enabled bool) *Cleaner {
	return &Cleaner{
		enabled:               enabled,
		multipleSpacesRegex:   regexp.MustCompile(`\s+`),
		multipleNewlinesRegex: regexp.MustCompile(`\n{3,}`),
		controlCharsRegex:     regexp.MustCompile(`[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]`),
		htmlTagsRegex:         regexp.MustCompile(`<[^>]*>`),
	}
}

func (c *Cleaner) Clean(text string) string {
	if !c.enabled {
		return text
	}

	cleaned := text

	cleaned = c.htmlTagsRegex.ReplaceAllString(cleaned, "")

	cleaned = c.controlCharsRegex.ReplaceAllString(cleaned, "")

	cleaned = c.multipleSpacesRegex.ReplaceAllString(cleaned, " ")

	cleaned = c.multipleNewlinesRegex.ReplaceAllString(cleaned, "\n\n")

	cleaned = strings.TrimSpace(cleaned)

	cleaned = c.removeOCRArtifacts(cleaned)

	return cleaned
}

func (c *Cleaner) removeOCRArtifacts(text string) string {
	lines := strings.Split(text, "\n")
	var cleanedLines []string
	
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if len(trimmed) > 1 && !c.isOCRArtifact(trimmed) {
			cleanedLines = append(cleanedLines, line)
		}
	}
	
	return strings.Join(cleanedLines, "\n")
}

func (c *Cleaner) isOCRArtifact(line string) bool {
	trimmed := strings.TrimSpace(line)
	
	if len(trimmed) == 1 {
		return true
	}
	
	if regexp.MustCompile(`^[^a-zA-Z]*$`).MatchString(trimmed) && len(trimmed) < 4 {
		return true
	}
	
	commonArtifacts := []string{"___", "---", "...", "|||", "^^^"}
	for _, artifact := range commonArtifacts {
		if strings.Contains(trimmed, artifact) && len(trimmed) < 10 {
			return true
		}
	}
	
	return false
}

func (c *Cleaner) CountWords(text string) int {
	if text == "" {
		return 0
	}
	
	fields := strings.Fields(text)
	wordCount := 0
	
	for _, field := range fields {
		if c.containsAlphanumeric(field) {
			wordCount++
		}
	}
	
	return wordCount
}

func (c *Cleaner) containsAlphanumeric(s string) bool {
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			return true
		}
	}
	return false
}

func (c *Cleaner) RemoveExtraWhitespace(text string) string {
	lines := strings.Split(text, "\n")
	var cleanedLines []string
	
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed != "" {
			cleanedLines = append(cleanedLines, trimmed)
		}
	}
	
	return strings.Join(cleanedLines, "\n")
}

func (c *Cleaner) NormalizeSpacing(text string) string {
	normalized := c.multipleSpacesRegex.ReplaceAllString(text, " ")
	return strings.TrimSpace(normalized)
}

func (c *Cleaner) ExtractSentences(text string) []string {
	if text == "" {
		return []string{}
	}
	
	sentenceRegex := regexp.MustCompile(`[.!?]+\s+`)
	sentences := sentenceRegex.Split(text, -1)
	
	var cleanedSentences []string
	for _, sentence := range sentences {
		trimmed := strings.TrimSpace(sentence)
		if len(trimmed) > 10 { 
			cleanedSentences = append(cleanedSentences, trimmed)
		}
	}
	
	return cleanedSentences
}