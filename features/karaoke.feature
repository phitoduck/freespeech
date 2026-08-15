Feature: Reading a page aloud with the words lit up
  The reader presses play. Adam's voice reads the page, and the word currently
  being spoken is highlighted, so a reader can follow along by eye and ear at
  once.

  Rule: playback highlights exactly one word at a time

    @docs
    Scenario: Pressing play starts the narration and lights the first word
      Given a PDF containing the text "One two three. Four five six."
      And I have dropped it onto the drop zone
      When I press play
      Then audio is playing
      And the word "One" is highlighted
      And no other word is highlighted

    # Tagged @gif as well: this is the scenario that records the animation in
    # the docs, so it deliberately reads a longer passage than its siblings —
    # a highlight crossing three sentences is the thing worth showing.
    @docs @gif
    Scenario: The highlight advances through the page as the audio plays
      Given a PDF containing the text "The quick brown fox jumps over the lazy dog. Kokoro reads this page aloud, one sentence at a time. Each word lights up as it is spoken."
      And I have dropped it onto the drop zone
      When I press play
      And the audio reaches the end of the first sentence
      Then the word "Kokoro" is highlighted
      And the word "The" is no longer highlighted

    # The highlight is the product. Every other scenario here checks the DOM
    # attribute, which would still pass if the highlight rendered invisibly.
    @docs
    Scenario: The highlighted word is visibly distinct from the words around it
      Given a PDF containing the text "One two three. Four five six."
      And I have dropped it onto the drop zone
      When I press play
      Then the highlighted word has a different background from the page
      And the highlighted word has a different background from its neighbours

    @docs
    Scenario: Pausing freezes the highlight where it is
      Given a PDF containing the text "One two three. Four five six."
      And I have dropped it onto the drop zone
      When I press play
      And I press pause
      Then audio is not playing
      And exactly one word is still highlighted

    @docs
    Scenario: Clicking a word jumps the narration to it
      Given a PDF containing the text "One two three. Four five six."
      And I have dropped it onto the drop zone
      When I click the word "Four"
      Then the narration position is at the word "Four"
      And the word "Four" is highlighted

  Rule: a document longer than one page can be read all the way through

    The API has always served any page. The reader only ever showed the first
    one, with nothing on screen to say more existed — so most of a document was
    unreachable.

    @docs
    Scenario: Moving to the next page
      Given a two-page PDF reading "Page one has some words." and "Page two has different words."
      And I have dropped it onto the drop zone
      Then I see "Page 1 of 2"
      When I go to the next page
      Then I see "Page 2 of 2"
      And the page shows the words:
        | Page |
        | two  |

    @docs
    Scenario: Going back to re-read the previous page
      Given a two-page PDF reading "Page one has some words." and "Page two has different words."
      And I have dropped it onto the drop zone
      When I go to the next page
      And I go to the previous page
      Then I see "Page 1 of 2"
      And the page shows the words:
        | Page |
        | one  |

    # Reachable in practice: narration takes seconds, so a reader who presses
    # Next twice has two requests in flight. If the earlier one answers last it
    # overwrites the newer, and the reader is left looking at one page's words
    # while hearing another — which makes every timing guarantee meaningless.
    @docs
    Scenario: A slow page never overwrites the page that replaced it
      Given a three-page PDF
      And I have dropped it onto the drop zone
      When I move forward twice and the first request answers last
      Then the words on screen and the narration are for the same page

    @docs
    Scenario: A one-page PDF shows no page controls at all
      Given a PDF containing the text "Just the one page."
      When I drop it onto the drop zone
      Then there are no page controls

    # Real PDFs have pages with no text of their own -- section dividers, the
    # back of a title page -- and upload only rejects a document when EVERY
    # page lacks text (see "A PDF with no readable text..." in upload.feature).
    # So a blank page in the middle of an otherwise-readable document reaches
    # the reader, and today it reproduces that same scenario's bug one level
    # down: an empty reading area, a Play button that is enabled but does
    # nothing when clicked, and nothing on screen to explain why.
    @docs
    Scenario: A blank page says so instead of looking broken
      Given a three-page PDF whose middle page is blank
      And I have dropped it onto the drop zone
      When I advance to the next page
      Then I see "This page has no text"
      And the play button is disabled
      When I advance to the next page
      Then the page shows the words:
        | Third |

  Rule: a page that cannot be narrated says so, instead of looking like it is loading

    Reported from real use: a reader opened a PDF, moved to a page with text,
    and the Play button stayed greyed out for good while clicking a word did
    nothing. Both are exactly right *while the narration is still loading*, and
    nothing on screen told the two apart. The failure was caught and stored all
    along — but the only place the app renders an error is inside the drop
    zone, which is no longer on screen once a page is showing, so it was
    written to a state slot nothing could display.

    @docs
    Scenario: A page whose narration fails says so, and offers to try again
      Given a two-page PDF reading "Page one has some words." and "Page two has different words."
      And I have dropped it onto the drop zone
      When the next page's narration fails
      Then I see the error "This page could not be read aloud"
      And the play button is disabled
      When I try again
      Then the play button is enabled
      And the error is gone

    # Documents live in the API's memory only (ADR 0005), so restarting it
    # leaves the open document's id pointing at nothing and every page of it
    # 404s. Trying again can never fix that — the reader has to hand the file
    # over a second time, and needs telling so rather than being offered a
    # button that will fail identically for as long as they keep pressing it.
    @docs
    Scenario: A document the server has forgotten asks for the PDF again
      Given a two-page PDF reading "Page one has some words." and "Page two has different words."
      And I have dropped it onto the drop zone
      When the server forgets the document and I go to the next page
      Then I see the error "The reader lost that document — drop the PDF again"
      And the drop zone is ready to accept a file again

  Rule: the timeline is a total, ordered cover of the audio

    These are the properties that make the highlight trustworthy. The timeline
    is derived — Kokoro returns no word timestamps — so every guarantee the UI
    relies on has to be proved here rather than assumed.

    # The whole timing design rests on each synthesis unit being short enough
    # that its measured duration re-anchors the estimate. Real documents break
    # that assumption: bullet lists, headings, tables and CVs carry no full
    # stops, so a naive split produced units of 50, 109 and even 262 words —
    # 262 words of audio whose word timings are estimated with no re-anchor at
    # all. Measured on real PDFs: 10 of 46 units exceeded 30 words.
    @property
    Scenario: No synthesis unit is long enough for timing to drift
      Given any page of words, punctuated or not
      When it is split into synthesis units
      Then no unit is longer than 30 words
      And no unit is longer than the limit the splitter declares
      And the units together still contain every word, in order

    @property
    Scenario: Any page's timeline covers its audio exactly once
      Given any page of words and any audio duration
      When a timeline is built for them
      Then the spans are in ascending order
      And no two spans overlap
      And there are no gaps between spans
      And the first span starts at 0.0
      And the last span ends at the audio duration

    @property
    Scenario: Any page's timeline has one span per word
      Given any page of words and any audio duration
      When a timeline is built for them
      Then there is exactly one span per word, in the same order

    @property
    Scenario: Every word is given a share of the audio
      Given any page of words and any audio duration
      When a timeline is built for them
      Then every span has a positive duration

    # `speech_cost` had no property of its own: the "longer words" scenario
    # below orders its pairs *by* speech_cost, so it checks that allocate
    # respects that order, never that the order is right. Digits fell straight
    # through — "2024", "1250000" and "2024-08-15" all cost exactly 1.00, less
    # than the word "we", while being 11.1% of tokens in real PDFs.
    @property
    Scenario: A number is given time in proportion to how long it takes to say
      Given any two numbers where the first has more digits than the second
      Then the first is allotted at least as much time as the second
      And a number is never quicker to say than a single letter

    @property
    Scenario: Longer words are never given less time than shorter ones
      Given any two words where the first takes longer to say than the second
      When a timeline is built for a page containing both
      Then the first word's span is at least as long as the second's

    @property
    Scenario: Looking up the spoken word is defined at every instant
      Given any page of words and any audio duration
      When a timeline is built for them
      Then looking up any instant inside the audio returns exactly one word
      And the word returned never moves backwards as the instant advances
