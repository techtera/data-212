declare module "react-image-annotate" {
  import { ComponentType } from "react";

  export interface AnnotatorImage {
    src: string;
    id?: string;
    regions?: Array<{
      points: number[][];
      className: string;
      id?: string;
    }>;
  }

  export interface AnnotatorProps {
    images?: AnnotatorImage[];
    videoSrc?: string;
    allowedArea?: string;
    selectedImage?: number;
    showPointDistances?: boolean;
    pointDistancePrecision?: number;
    showTags?: boolean;
    enabledTools?: string[];
    selectedTool?: string;
    regionTagList?: string[];
    regionClsList?: string[];
    imageTagList?: string[];
    imageClsList?: string[];
    keyframes?: Record<string, any>;
    taskDescription?: string;
    fullImageSegmentationMode?: boolean;
    RegionEditLabel?: React.ComponentType<any>;
    videoTime?: number;
    videoName?: string;
    onExit?: (state: any) => void;
    onNextImage?: () => void;
    onPrevImage?: () => void;
    keypointDefinitions?: any[];
    autoSegmentationOptions?: { type: string };
    hideHeader?: boolean;
    hideHeaderText?: boolean;
    hideNext?: boolean;
    hidePrev?: boolean;
    allowComments?: boolean;
  }

  const Annotator: ComponentType<AnnotatorProps>;
  export { Annotator };
  export default Annotator;
}