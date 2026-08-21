       IDENTIFICATION DIVISION.
       PROGRAM-ID. SAMPLE.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-NAME       PIC X(20) VALUE 'WORLD'.
       01  WS-COUNT      PIC 9(3) VALUE 1.

       PROCEDURE DIVISION.
           DISPLAY 'HELLO, ' WS-NAME.
           IF WS-COUNT > 0
               DISPLAY 'COUNT IS POSITIVE'
           ELSE
               DISPLAY 'COUNT IS ZERO'
           END-IF.
           STOP RUN.
