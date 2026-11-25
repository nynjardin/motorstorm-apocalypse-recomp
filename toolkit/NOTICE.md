# Third-party code in this directory

`ps3recomp_local.diff` and `new_files/` are changes to **ps3recomp**
(<https://github.com/sp00nznet/ps3recomp>, MIT). The diff quotes parts of its sources, and the
new files are written against them.

`new_files/tools/ppu_lifter_lr.py` is ps3recomp's `tools/ppu_lifter.py` with the local-register
lifter of **motorstorm-apocalypse-pc**
(<https://github.com/millennium-h4x0r/motorstorm-apocalypse-pc>, MIT) merged in
(our patch #58).

Both are distributed under the MIT License:

```
MIT License

Copyright (c) 2026 Ned Heller / sp00nznet
Copyright (c) 2026 the motorstorm-apocalypse-recomp contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
