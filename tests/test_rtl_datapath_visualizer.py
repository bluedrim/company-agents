from pathlib import Path
import tempfile
import unittest

from rtl_datapath_visualizer import build_design, emit_datapath_dot, emit_hierarchy_dot, parse_filelist


SAMPLE_RTL = """
module producer(output logic [31:0] data_o, output logic valid_o);
endmodule

module consumer(input logic [31:0] data_i, input logic valid_i);
endmodule

module control_block(input logic clk, input logic reset_n);
endmodule

module top(input logic clk, input logic reset_n);
  wire [31:0] data_bus;
  wire valid_bus;

  producer u_producer (
    .data_o(data_bus),
    .valid_o(valid_bus)
  );

  consumer u_consumer (
    .data_i(data_bus),
    .valid_i(valid_bus)
  );

  control_block u_control (
    .clk(clk),
    .reset_n(reset_n)
  );
endmodule
"""

MULTI_INSTANCE_RTL = """
module producer(output logic [15:0] data_o);
endmodule

module consumer(input logic [15:0] data_i);
endmodule

module top;
  wire [15:0] data_a;
  wire [15:0] data_b;

  producer u_producer_a (.data_o(data_a)),
           u_producer_b (.data_o(data_b));

  consumer u_consumer_a (.data_i({data_a[7:0], data_b[7:0]}));
endmodule
"""


class RtlDatapathVisualizerTest(unittest.TestCase):
    def test_nested_filelist_and_signal_level_datapath_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rtl = root / "sample.sv"
            rtl.write_text(SAMPLE_RTL, encoding="utf-8")
            nested = root / "nested.f"
            nested.write_text("sample.sv\n", encoding="utf-8")
            filelist = root / "filelist.f"
            filelist.write_text("+incdir+include\n-f nested.f\n", encoding="utf-8")

            self.assertEqual(parse_filelist(filelist), [rtl.resolve()])
            design = build_design(filelist, explicit_top="top")

            self.assertEqual(design.top, "top")
            self.assertEqual(len(design.hierarchy_edges), 3)
            self.assertEqual(len(design.data_edges), 1)
            self.assertEqual(design.data_edges[0].net, "data_bus")

            hierarchy_dot = emit_hierarchy_dot(design)
            datapath_dot = emit_datapath_dot(design)
            self.assertIn("producer", hierarchy_dot)
            self.assertIn("data_bus @ top", datapath_dot)
            self.assertNotIn("valid_bus @ top", datapath_dot)

    def test_multi_instance_declaration_and_concat_connections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rtl = root / "multi.sv"
            rtl.write_text(MULTI_INSTANCE_RTL, encoding="utf-8")
            filelist = root / "filelist.f"
            filelist.write_text("multi.sv\n", encoding="utf-8")

            design = build_design(filelist, explicit_top="top")

            self.assertEqual(len(design.hierarchy_edges), 3)
            self.assertEqual({edge.net for edge in design.data_edges}, {"data_a", "data_b"})
            self.assertIn("u_producer_a:producer.data_o", {edge.source for edge in design.data_edges})
            self.assertIn("u_producer_b:producer.data_o", {edge.source for edge in design.data_edges})
            self.assertEqual({edge.target for edge in design.data_edges}, {"u_consumer_a:consumer.data_i"})


if __name__ == "__main__":
    unittest.main()
