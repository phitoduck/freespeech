Feature: Dropping a PDF onto the reader
  A reader arrives with a PDF on their desktop. They should be able to drag it
  onto the page and immediately see its words, with no dialog, no settings, and
  no account.

  Rule: the drop zone accepts a PDF and shows its first page

    @docs
    Scenario: Dropping a one-page PDF reveals its text
      Given a PDF containing the text "The quick brown fox jumps over the lazy dog."
      When I drop it onto the drop zone
      Then the reader shows 1 page
      And the page shows the words:
        | The   |
        | quick |
        | brown |
        | fox   |
      And the play button is enabled

    # Scanned PDFs are images with no text layer. Without this the reader shows
    # a blank page and an enabled play button that does nothing, and never says
    # why. A blank *first page* is not enough — cover pages are common — so this
    # only fires when the whole document has no readable text.
    @docs
    Scenario: A PDF with no readable text says so instead of going blank
      Given a PDF containing no text at all
      When I drop it onto the drop zone
      Then I see the error "That PDF has no readable text — it may be a scan"
      And the drop zone is still ready to accept a file

    # A locked PDF is a perfectly valid PDF. Telling the reader it is "not a
    # valid PDF" sends them off to re-export a file that was never broken.
    #
    # Tagged @docs because that tag selects *browser* scenarios, not because
    # these emit an image — their screenshots would be the rejection shot
    # again, which teaches nothing (ADR 0004).
    @docs
    Scenario: A password-protected PDF says it is locked, not that it is broken
      Given a password-protected PDF
      When I drop it onto the drop zone
      Then I see the error "That PDF is password-protected"

    # A file that really is corrupt should say so once, not twice: the message
    # was "not a valid PDF: not a valid PDF".
    @docs
    Scenario: A corrupt file named .pdf is reported once, clearly
      Given a corrupt file named "broken.pdf"
      When I drop it onto the drop zone
      Then I see the error "That file is not a readable PDF"

    @docs
    Scenario: A non-PDF file is rejected without breaking the page
      Given a file named "notes.txt" containing "this is not a pdf"
      When I drop it onto the drop zone
      Then I see the error "Only PDF files are supported"
      And the drop zone is still ready to accept a file

  Rule: extraction preserves the document's reading order

    @property
    Scenario: Any text survives the round trip through a PDF
      Given any document of words
      When it is rendered to a PDF and extracted again
      Then the extracted words are exactly the original words, in order

    @property
    Scenario: Every extracted word carries a usable highlight box
      Given any document of words
      When it is rendered to a PDF and extracted again
      Then every word has a box with positive width and height
      And every word's box lies inside its page
