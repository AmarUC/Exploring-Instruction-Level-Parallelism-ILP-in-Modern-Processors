# gem5 SE mode needs statically linked x86-64 binaries.
CC      ?= gcc
CFLAGS  ?= -O2 -static -Wall
# Keep branchy's if/else a real branch (otherwise gcc emits cmov and there is nothing to predict)
BRFLAGS  = -fno-if-conversion -fno-if-conversion2 -fno-tree-vectorize

BINS = hello intalu fpu memory branchy
all: $(BINS)

branchy: branchy.c
	$(CC) $(CFLAGS) $(BRFLAGS) -o $@ $<

%: %.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(BINS)

.PHONY: all clean
