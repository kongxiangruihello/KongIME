import Foundation
import CoreGraphics

enum CandidateGeometry {
  // Cocoa screen coordinates grow upwards. Include the complete window (footer
  // included) before placement; clamping an oversized window must not cover the line.
  static func avoidingLine(_ proposed: CGRect, anchor: CGRect, in area: CGRect, gap: CGFloat) -> CGRect {
    let gap = max(0, gap)
    let belowTop = min(area.maxY, max(area.minY, anchor.minY - gap))
    let aboveBottom = min(area.maxY, max(area.minY, anchor.maxY + gap))
    let below = belowTop - area.minY, above = area.maxY - aboveBottom
    let useBelow = proposed.height <= below || (proposed.height > above && below >= above)
    let height = min(proposed.height, useBelow ? below : above)
    let width = min(proposed.width, area.width)
    return CGRect(x: min(max(proposed.minX, area.minX), area.maxX-width),
                  y: useBelow ? belowTop-height : aboveBottom, width: width, height: height)
  }
  static func screenIndex(anchor: CGRect, frames: [CGRect]) -> Int? {
    frames.indices.min { left, right in
      func distance(_ frame: CGRect) -> CGFloat {
        let dx = max(frame.minX - anchor.midX, 0, anchor.midX - frame.maxX)
        let dy = max(frame.minY - anchor.midY, 0, anchor.midY - frame.maxY)
        return dx * dx + dy * dy
      }
      return distance(frames[left]) < distance(frames[right])
    }
  }
  static func contained(_ proposed: CGRect, in area: CGRect) -> CGRect {
    let size = CGSize(width: min(proposed.width, area.width), height: min(proposed.height, area.height))
    return CGRect(x: min(max(proposed.minX, area.minX), area.maxX-size.width),
                  y: min(max(proposed.minY, area.minY), area.maxY-size.height), width: size.width, height: size.height)
  }
}
