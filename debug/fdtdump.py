import struct, sys

def parse(path):
    b = open(path,'rb').read()
    magic, total, off_s, off_str, off_rsv, ver, lcv, cpuid, sz_str, sz_s = struct.unpack('>10I', b[:40])
    assert magic == 0xd00dfeed, hex(magic)
    strs = b[off_str:off_str+sz_str]
    p, depth, stack, out = off_s, 0, [], []
    while True:
        tok, = struct.unpack('>I', b[p:p+4]); p += 4
        if tok == 1:
            e = b.index(b'\0', p); name = b[p:e].decode()
            p = (e + 4) & ~3
            stack.append(name)
        elif tok == 2:
            stack.pop()
        elif tok == 3:
            ln, no = struct.unpack('>2I', b[p:p+8]); p += 8
            data = b[p:p+ln]; p = (p + ln + 3) & ~3
            e = strs.index(b'\0', no); pname = strs[no:e].decode()
            path_s = '/' + '/'.join(x for x in stack[1:])
            out.append((path_s + '/' + pname, fmt(data)))
        elif tok == 4:
            continue
        elif tok == 9:
            break
        else:
            raise SystemExit('bad token %d at %d' % (tok, p))
    return dict(out)

def fmt(d):
    if not d: return '<empty>'
    if d[-1] == 0 and all(32 <= c < 127 or c == 0 for c in d[:-1]) and len(d) > 1:
        return '"' + '","'.join(x.decode() for x in d[:-1].split(b'\0')) + '"'
    if len(d) % 4 == 0 and len(d) <= 64:
        return '<' + ' '.join('0x%08x' % v for v in struct.unpack('>%dI' % (len(d)//4), d)) + '>'
    return '[%d bytes] %s' % (len(d), d[:32].hex())

if __name__ == '__main__':
    d = parse(sys.argv[1])
    for k in sorted(d):
        print('%s = %s' % (k, d[k]))
