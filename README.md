# RTL DataPath Visualizer

`rte` 스타일 filelist(`.f`)를 읽어서 신규 입사자가 RTL 구조를 빠르게 볼 수 있도록 두 가지 그림을 생성합니다.

1. **모듈 계층도**: 어떤 모듈이 어떤 하위 모듈을 인스턴스하는지 표시
2. **추정 datapath 그래프**: 하위 인스턴스들이 공유하는 net을 기준으로 `output -> input` data 흐름을 표시

## 사용 방법

```bash
python3 rtl_datapath_visualizer.py <filelist.f> [--top TOP_MODULE] [--out-prefix rtl_datapath] [--no-png]
```

예시:

```bash
python3 rtl_datapath_visualizer.py ./rte/filelist.f --top top
```

## 출력물

기본 prefix가 `rtl_datapath`일 때 아래 파일이 생성됩니다.

- `rtl_datapath_hierarchy.dot`: 전체 모듈 계층 Graphviz DOT
- `rtl_datapath_datapath.dot`: signal-level datapath Graphviz DOT
- `rtl_datapath_hierarchy.png`: Graphviz `dot`가 설치되어 있으면 자동 생성
- `rtl_datapath_datapath.png`: Graphviz `dot`가 설치되어 있으면 자동 생성

PNG 생성이 필요 없으면 `--no-png`를 사용하세요. 기존 사용자를 위해 `--out <path>`와 `--png <path>`도 계속 받을 수 있습니다. `--out rtl_datapath.dot`처럼 `.dot` 파일명을 넘기면 prefix는 `rtl_datapath`로 해석됩니다.

## 표시 규칙

### 모듈 계층도

- **파란색 노드**: top module
- **주황색 노드/엣지**: datapath 가능성이 높은 모듈/연결
  - 이름에 `data`, `alu`, `mul`, `adder`, `fifo`, `regfile`, `pipe`, `mem`, `payload`, `operand`, `result` 등의 키워드가 포함된 경우
- **회색 노드/엣지**: 일반 제어/기타 연결

### Datapath 그래프

- 하위 모듈 인스턴스의 port 방향을 사용해 같은 net에 연결된 `output -> input` edge를 생성합니다.
- `clk`, `reset`, `valid`, `ready`, `enable`, `stall`, `flush`, `ctrl` 같은 제어성 net은 제외해 datapath 위주로 보이게 합니다.
- Edge label은 `<net 이름> @ <상위 모듈>` 형식입니다.

## 지원 filelist 문법

- Verilog/SystemVerilog 파일 경로 (`.v`, `.sv`, `.vh`, `.svh`)
- 중첩 filelist: `-f other.f`, `-F other.f`, `-fother.f`
- 라이브러리 파일: `-v <file>`
- 라이브러리 디렉터리: `-y <dir>` (해당 디렉터리 바로 아래의 RTL 파일 포함)
- include/define 옵션: `+incdir+...`, `+define+...` (그림 생성에는 필요 없으므로 무시)
- 환경변수/홈 디렉터리 확장: `$RTL_DIR/foo.sv`, `~/rtl/foo.sv`
- 주석/빈 줄

## 한계와 권장 사용법

이 도구는 별도 EDA parser 없이 Python 표준 라이브러리만 사용하는 경량 분석기입니다. 일반적인 모듈 선언, named/ordered port connection, parameterized instance, 한 문장에 여러 개가 선언된 instance, slice/concatenation 기반 port connection은 처리하지만, 복잡한 macro expansion이나 generate로 만들어지는 모든 구조를 완벽하게 elaboration하지는 않습니다.

정확도를 높이려면 다음을 권장합니다.

- `--top`으로 top module을 명시합니다.
- datapath net/port/module 이름에 `data`, `payload`, `operand`, `result`처럼 의미 있는 이름을 사용합니다.
- 제어 신호는 `valid`, `ready`, `clk`, `reset`, `ctrl` 등 명확한 이름을 사용하면 datapath 그래프에서 자동 제외됩니다.
